"""Tests for scoped role-based authorization."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import SYSTEM_ROLES, Permission, ScopeType, SystemRole, expand
from app.models import Role
from app.services.authorization import (
    INSTANCE,
    AuthorizationError,
    ConflictError,
    InvalidRequestError,
    ScopeRef,
    assign_role,
    create_custom_role,
    delete_custom_role,
    get_role,
    has_permission,
    is_last_platform_admin,
    lineage,
    permissions_at,
    revoke_assignment,
    sync_system_roles,
    update_custom_role,
    user_assignments,
)
from tests.authz_helpers import ScopeTree, curriculum_scopes, grant, new_faculty, new_user

pytestmark = pytest.mark.usefixtures("system_roles")


@pytest.fixture
def tree() -> Iterator[ScopeTree]:
    with curriculum_scopes() as scopes:
        yield scopes


async def scope_of_type(db: AsyncSession, tree: ScopeTree, scope_type: ScopeType) -> ScopeRef:
    """A fresh scope of the given type, with its own ancestors."""
    if scope_type == ScopeType.INSTANCE:
        return INSTANCE
    _, faculty = await new_faculty(db)
    if scope_type == ScopeType.FACULTY:
        return faculty
    programme = tree.programme(faculty)
    if scope_type == ScopeType.PROGRAMME:
        return programme
    module = tree.module(programme)
    if scope_type == ScopeType.MODULE:
        return module
    return tree.learning_event(module)


ROLE_SCOPE_PAIRS = [
    (role, scope_type) for role in SYSTEM_ROLES for scope_type in sorted(role.scope_types)
]


class TestPermissionMatrix:
    """Every system role, at every scope type it allows, against every permission."""

    @pytest.mark.parametrize(
        ("role", "scope_type"),
        ROLE_SCOPE_PAIRS,
        ids=[f"{r.key}@{s}" for r, s in ROLE_SCOPE_PAIRS],
    )
    async def test_role_grants_exactly_its_permissions(
        self, db_session: AsyncSession, tree: ScopeTree, role: SystemRole, scope_type: ScopeType
    ) -> None:
        user = await new_user(db_session)
        scope = await scope_of_type(db_session, tree, scope_type)
        expires = datetime.now(UTC) + timedelta(days=30) if role.requires_expiry else None
        await grant(db_session, user, role.key, scope, expires)

        granted = await permissions_at(db_session, user, scope)

        assert granted == expand(role.permissions)
        for permission in Permission:
            expected = permission in expand(role.permissions)
            assert await has_permission(db_session, user, permission, scope) is expected

    @pytest.mark.parametrize(
        ("role", "scope_type"),
        [(r, s) for r, s in ROLE_SCOPE_PAIRS if s != ScopeType.INSTANCE],
        ids=[f"{r.key}@{s}" for r, s in ROLE_SCOPE_PAIRS if s != ScopeType.INSTANCE],
    )
    async def test_scoped_role_does_not_reach_parent_or_sibling(
        self, db_session: AsyncSession, tree: ScopeTree, role: SystemRole, scope_type: ScopeType
    ) -> None:
        user = await new_user(db_session)
        scope = await scope_of_type(db_session, tree, scope_type)
        sibling = await scope_of_type(db_session, tree, scope_type)
        expires = datetime.now(UTC) + timedelta(days=30) if role.requires_expiry else None
        await grant(db_session, user, role.key, scope, expires)

        parent = (await lineage(db_session, scope))[1]
        assert await permissions_at(db_session, user, parent) == frozenset()
        assert await permissions_at(db_session, user, sibling) == frozenset()


class TestHierarchy:
    async def test_role_applies_to_everything_inside_its_scope(
        self, db_session: AsyncSession, tree: ScopeTree
    ) -> None:
        user = await new_user(db_session)
        _, faculty = await new_faculty(db_session)
        programme = tree.programme(faculty)
        session = tree.learning_event(tree.module(programme))
        await grant(db_session, user, "curriculum_office", faculty)

        for scope in (faculty, programme, session):
            assert await has_permission(db_session, user, Permission.CURRICULUM_EDIT, scope)
        assert not await has_permission(db_session, user, Permission.CURRICULUM_EDIT, INSTANCE)

    async def test_instance_role_applies_everywhere(
        self, db_session: AsyncSession, tree: ScopeTree
    ) -> None:
        user = await new_user(db_session)
        await grant(db_session, user, "platform_admin")
        _, faculty = await new_faculty(db_session)
        module = tree.module(tree.programme(faculty))

        assert await has_permission(db_session, user, Permission.SETTINGS_MANAGE, module)

    async def test_roles_at_several_scopes_combine(
        self, db_session: AsyncSession, tree: ScopeTree
    ) -> None:
        user = await new_user(db_session)
        _, faculty = await new_faculty(db_session)
        programme = tree.programme(faculty)
        module = tree.module(programme)
        await grant(db_session, user, "student", INSTANCE)
        await grant(db_session, user, "lecturer", module)

        at_module = await permissions_at(db_session, user, module)
        at_programme = await permissions_at(db_session, user, programme)

        assert Permission.OBJECTIVES_EDIT in at_module
        assert Permission.CURRICULUM_VIEW_PUBLISHED in at_programme
        assert Permission.OBJECTIVES_EDIT not in at_programme

    async def test_view_implies_view_published(self, db_session: AsyncSession) -> None:
        assert Permission.CURRICULUM_VIEW_PUBLISHED in expand({Permission.CURRICULUM_VIEW})

    async def test_unknown_scope(self, db_session: AsyncSession) -> None:
        import uuid

        with pytest.raises(InvalidRequestError, match="No faculty"):
            await lineage(db_session, ScopeRef(ScopeType.FACULTY, uuid.uuid4()))

    async def test_scope_type_not_available_yet(self, db_session: AsyncSession) -> None:
        import uuid

        with pytest.raises(InvalidRequestError, match="not available yet"):
            await lineage(db_session, ScopeRef(ScopeType.MODULE, uuid.uuid4()))

    def test_instance_scope_has_no_id(self) -> None:
        import uuid

        with pytest.raises(InvalidRequestError):
            ScopeRef(ScopeType.INSTANCE, uuid.uuid4())
        with pytest.raises(InvalidRequestError):
            ScopeRef(ScopeType.FACULTY)


class TestConditions:
    async def test_no_roles_no_permissions(self, db_session: AsyncSession) -> None:
        user = await new_user(db_session)

        assert await permissions_at(db_session, user, INSTANCE) == frozenset()

    async def test_inactive_user_has_no_permissions(self, db_session: AsyncSession) -> None:
        user = await new_user(db_session)
        await grant(db_session, user, "platform_admin")
        user.is_active = False

        assert not await has_permission(db_session, user, Permission.USERS_MANAGE)

    async def test_expired_assignment_is_ignored(
        self, db_session: AsyncSession, tree: ScopeTree
    ) -> None:
        user = await new_user(db_session)
        programme = tree.programme((await new_faculty(db_session))[1])
        assignment = await grant(
            db_session,
            user,
            "external_reviewer",
            programme,
            datetime.now(UTC) + timedelta(days=1),
        )
        assert await has_permission(db_session, user, Permission.EVIDENCE_VIEW, programme)

        assignment.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        await db_session.flush()

        assert not await has_permission(db_session, user, Permission.EVIDENCE_VIEW, programme)
        assert await user_assignments(db_session, user.id) == []


class TestAssignValidation:
    async def test_wrong_scope_type_for_role(self, db_session: AsyncSession) -> None:
        user = await new_user(db_session)

        with pytest.raises(InvalidRequestError, match="can only be assigned at"):
            await grant(db_session, user, "programme_director", INSTANCE)

    async def test_external_reviewer_needs_end_date(
        self, db_session: AsyncSession, tree: ScopeTree
    ) -> None:
        user = await new_user(db_session)
        programme = tree.programme((await new_faculty(db_session))[1])

        with pytest.raises(InvalidRequestError, match="end date"):
            await grant(db_session, user, "external_reviewer", programme)

    async def test_end_date_must_be_in_future(self, db_session: AsyncSession) -> None:
        user = await new_user(db_session)

        with pytest.raises(InvalidRequestError, match="future"):
            await grant(db_session, user, "student", INSTANCE, datetime.now(UTC))

    async def test_duplicate_assignment(self, db_session: AsyncSession) -> None:
        user = await new_user(db_session)
        await grant(db_session, user, "student")

        with pytest.raises(ConflictError):
            await grant(db_session, user, "student")

    async def test_deleted_user(self, db_session: AsyncSession) -> None:
        user = await new_user(db_session)
        user.soft_delete()

        with pytest.raises(InvalidRequestError, match="deleted"):
            await grant(db_session, user, "student")


class TestNoEscalation:
    """Granting a role needs roles.assign at the scope and all of the role's permissions."""

    async def assign(
        self,
        db: AsyncSession,
        actor_role: str,
        actor_scope: ScopeRef,
        role_key: str,
        scope: ScopeRef,
    ) -> None:
        actor = await new_user(db)
        await grant(db, actor, actor_role, actor_scope)
        target = await new_user(db)
        role = await get_role(db, key=role_key)
        assert role is not None
        await assign_role(db, actor, user=target, role=role, scope=scope)

    async def test_director_can_staff_own_programme(
        self, db_session: AsyncSession, tree: ScopeTree
    ) -> None:
        programme = tree.programme((await new_faculty(db_session))[1])
        module = tree.module(programme)

        await self.assign(db_session, "programme_director", programme, "module_coordinator", module)
        await self.assign(db_session, "programme_director", programme, "lecturer", module)
        await self.assign(db_session, "programme_director", programme, "mapper", programme)

    async def test_director_cannot_staff_another_programme(
        self, db_session: AsyncSession, tree: ScopeTree
    ) -> None:
        _, faculty = await new_faculty(db_session)
        own, other = tree.programme(faculty), tree.programme(faculty)

        with pytest.raises(AuthorizationError, match="may not assign"):
            await self.assign(
                db_session, "programme_director", own, "module_coordinator", tree.module(other)
            )

    async def test_director_cannot_make_platform_admin(
        self, db_session: AsyncSession, tree: ScopeTree
    ) -> None:
        programme = tree.programme((await new_faculty(db_session))[1])

        with pytest.raises(AuthorizationError):
            await self.assign(
                db_session, "programme_director", programme, "platform_admin", INSTANCE
            )

    async def test_cannot_grant_permissions_one_lacks(
        self, db_session: AsyncSession, tree: ScopeTree
    ) -> None:
        programme = tree.programme((await new_faculty(db_session))[1])
        admin = await new_user(db_session)
        await create_custom_role(
            db_session,
            admin,
            key="framework_editor",
            name="Framework editor",
            description="",
            permissions=["frameworks.manage"],
            scope_types=["programme"],
            requires_expiry=False,
        )

        with pytest.raises(AuthorizationError, match="do not hold"):
            await self.assign(
                db_session, "programme_director", programme, "framework_editor", programme
            )

    async def test_coordinator_cannot_assign_anything(
        self, db_session: AsyncSession, tree: ScopeTree
    ) -> None:
        module = tree.module(tree.programme((await new_faculty(db_session))[1]))

        with pytest.raises(AuthorizationError):
            await self.assign(db_session, "module_coordinator", module, "lecturer", module)

    async def test_curriculum_office_staffs_its_faculty_only(
        self, db_session: AsyncSession, tree: ScopeTree
    ) -> None:
        _, faculty = await new_faculty(db_session)
        _, other_faculty = await new_faculty(db_session)

        await self.assign(
            db_session, "curriculum_office", faculty, "programme_director", tree.programme(faculty)
        )
        with pytest.raises(AuthorizationError):
            await self.assign(
                db_session,
                "curriculum_office",
                faculty,
                "programme_director",
                tree.programme(other_faculty),
            )


class TestRevoke:
    async def test_director_can_remove_staff_they_could_add(
        self, db_session: AsyncSession, tree: ScopeTree
    ) -> None:
        programme = tree.programme((await new_faculty(db_session))[1])
        module = tree.module(programme)
        director = await new_user(db_session)
        await grant(db_session, director, "programme_director", programme)
        coordinator = await new_user(db_session)
        assignment = await grant(db_session, coordinator, "module_coordinator", module)

        await revoke_assignment(db_session, director, assignment)

        assert await user_assignments(db_session, coordinator.id) == []

    async def test_cannot_remove_roles_above_own(
        self, db_session: AsyncSession, tree: ScopeTree
    ) -> None:
        programme = tree.programme((await new_faculty(db_session))[1])
        director = await new_user(db_session)
        await grant(db_session, director, "programme_director", programme)
        admin = await new_user(db_session)
        admin_assignment = await grant(db_session, admin, "platform_admin")

        with pytest.raises(AuthorizationError):
            await revoke_assignment(db_session, director, admin_assignment)

    async def test_last_platform_admin_is_kept(self, db_session: AsyncSession) -> None:
        admin = await new_user(db_session)
        assignment = await grant(db_session, admin, "platform_admin")
        assert await is_last_platform_admin(db_session, admin)

        with pytest.raises(ConflictError, match="last platform admin"):
            await revoke_assignment(db_session, admin, assignment)

        second = await new_user(db_session)
        await grant(db_session, second, "platform_admin")
        assert not await is_last_platform_admin(db_session, admin)
        await revoke_assignment(db_session, second, assignment)


class TestRoles:
    async def test_system_roles_are_synced(self, db_session: AsyncSession) -> None:
        for definition in SYSTEM_ROLES:
            role = await get_role(db_session, key=definition.key)
            assert role is not None
            assert role.is_system
            assert set(role.permissions) == {p.value for p in definition.permissions}
            assert set(role.scope_types) == {s.value for s in definition.scope_types}

    async def test_sync_is_idempotent_and_repairs_changes(self, db_session: AsyncSession) -> None:
        role = await get_role(db_session, key="student")
        assert role is not None
        role.permissions = ["users.manage"]
        await db_session.flush()

        await sync_system_roles(db_session)
        await sync_system_roles(db_session)

        assert role.permissions == ["curriculum.view_published"]

    async def custom(self, db: AsyncSession, **overrides: object) -> Role:
        admin = await new_user(db)
        values: dict[str, object] = {
            "key": "timetabler",
            "name": "Timetabler",
            "description": "Schedules sessions",
            "permissions": ["curriculum.view", "curriculum.edit"],
            "scope_types": ["faculty"],
            "requires_expiry": False,
            **overrides,
        }
        return await create_custom_role(db, admin, **values)  # type: ignore[arg-type]

    async def test_custom_role_can_be_assigned(self, db_session: AsyncSession) -> None:
        role = await self.custom(db_session)
        user = await new_user(db_session)
        _, faculty = await new_faculty(db_session)

        await grant(db_session, user, role.key, faculty)

        assert await has_permission(db_session, user, Permission.CURRICULUM_EDIT, faculty)
        assert not role.is_system

    @pytest.mark.parametrize(
        ("overrides", "message"),
        [
            ({"key": "Bad Key"}, "lowercase"),
            ({"permissions": ["curriculum.delete_everything"]}, "Unknown permissions"),
            ({"scope_types": ["galaxy"]}, "Unknown scope types"),
            ({"scope_types": []}, "at least one scope"),
        ],
    )
    async def test_invalid_custom_role(
        self, db_session: AsyncSession, overrides: dict[str, object], message: str
    ) -> None:
        with pytest.raises(InvalidRequestError, match=message):
            await self.custom(db_session, **overrides)

    @pytest.mark.parametrize("key", ["timetabler", "platform_admin"])
    async def test_role_keys_are_unique(self, db_session: AsyncSession, key: str) -> None:
        await self.custom(db_session)

        with pytest.raises(ConflictError):
            await self.custom(db_session, key=key)

    async def test_update_custom_role(self, db_session: AsyncSession) -> None:
        role = await self.custom(db_session)

        await update_custom_role(
            db_session,
            role,
            name="Scheduler",
            permissions=["curriculum.view"],
            scope_types=["faculty", "programme"],
            requires_expiry=True,
            description="x",
        )

        assert (role.name, role.permissions, role.scope_types, role.requires_expiry) == (
            "Scheduler",
            ["curriculum.view"],
            ["faculty", "programme"],
            True,
        )

    async def test_system_roles_cannot_be_changed_or_deleted(
        self, db_session: AsyncSession
    ) -> None:
        role = await get_role(db_session, key="student")
        assert role is not None

        with pytest.raises(ConflictError):
            await update_custom_role(db_session, role, name="Learner")
        with pytest.raises(ConflictError):
            await delete_custom_role(db_session, role)

    async def test_role_in_use_cannot_be_deleted(self, db_session: AsyncSession) -> None:
        role = await self.custom(db_session)
        user = await new_user(db_session)
        assignment = await grant(db_session, user, role.key, (await new_faculty(db_session))[1])

        with pytest.raises(ConflictError, match="still assigned"):
            await delete_custom_role(db_session, role)

        await db_session.delete(assignment)
        await db_session.flush()
        await delete_custom_role(db_session, role)
        assert await get_role(db_session, key="timetabler") is None
