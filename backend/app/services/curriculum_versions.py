"""Curriculum versions: publishing, copying a year forward and deleting drafts (ADR 030).

Permissions are checked by the API before these functions run; these functions
enforce the rules:

- Status changes follow ``TRANSITIONS``: a draft is published, a published version
  can go back to draft (to correct it) or be archived, and an archived version can
  be published again. Publishing needs at least one module.
- Only drafts can be changed (``curriculum_edit.EDITABLE_STATUSES``) or deleted.
  Deleting a draft is a soft delete of the version and everything in it, with one
  timestamp.
- Copying forward makes a new draft for another academic year of the same programme
  (``based_on_id`` points to the source), with every live phase, module, session and
  objective (programme outcomes too), upward links, tags and framework mappings with
  their review state. Each copied row records its original in ``based_on_id`` so the
  version diff can follow items across years. LMS references are not copied.
- Role assignments at module and session scope are copied for the assignments the
  caller picks from the preview (owner decision, Slice 1.2). Expired assignments,
  deactivated or deleted accounts, and roles the caller may not grant are skipped.

All changes go through ORM objects so the audit log records them (ADR 017).
"""

import uuid
from collections.abc import Collection
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.permissions import Permission, ScopeType
from app.models import (
    CurriculumVersion,
    LearningEvent,
    MappingLink,
    Module,
    Objective,
    Phase,
    RoleAssignment,
    User,
)
from app.models.curriculum import VersionStatus
from app.services.authorization import (
    ConflictError,
    InvalidRequestError,
    ScopeRef,
    assign_role,
    permissions_at,
    role_permissions,
)
from app.services.curriculum_copy import Copies, copy_children, copy_module_rows
from app.services.curriculum_edit import phase_siblings, soft_delete_assessments
from app.services.mapping_live import live_link, soft_delete_links

S = VersionStatus

# (from, to) -> the name of the change, used for audit labels and messages.
TRANSITIONS: dict[tuple[VersionStatus, VersionStatus], str] = {
    (S.DRAFT, S.PUBLISHED): "publish",
    (S.PUBLISHED, S.DRAFT): "unpublish",
    (S.PUBLISHED, S.ARCHIVED): "archive",
    (S.ARCHIVED, S.PUBLISHED): "unarchive",
}


def transition(version: CurriculumVersion, status: VersionStatus) -> str:
    """The name of the change from the version's status to ``status``.

    Raises:
        ConflictError: If the version cannot go to that status from its current one.
    """
    name = TRANSITIONS.get((version.status, status))
    if name is None or version.deleted_at is not None:
        raise ConflictError(f"A {version.status} version cannot be made {status}.")
    return name


async def _live_modules(db: AsyncSession, version_id: uuid.UUID) -> list[Module]:
    return list(
        await db.scalars(
            select(Module)
            .where(Module.version_id == version_id, Module.deleted_at.is_(None))
            .order_by(Module.position, Module.code)
        )
    )


async def change_status(
    db: AsyncSession, version: CurriculumVersion, status: VersionStatus
) -> CurriculumVersion:
    """Publish, unpublish, archive or unarchive a version.

    ``published_at`` is set whenever the version is published and cleared when it goes
    back to draft; archiving keeps it.

    Raises:
        ConflictError: If the change is not allowed, or a draft has no modules.
    """
    name = transition(version, status)
    if name == "publish" and not await _live_modules(db, version.id):
        raise ConflictError("Add at least one module before publishing this version.")
    version.status = status
    if status == S.PUBLISHED:
        version.published_at = datetime.now(UTC)
    elif status == S.DRAFT:
        version.published_at = None
    await db.flush()
    return version


async def delete_draft(db: AsyncSession, version: CurriculumVersion) -> None:
    """Soft-delete a draft version with everything in it.

    Raises:
        ConflictError: If the version is not a draft.
    """
    if version.status != S.DRAFT or version.deleted_at is not None:
        raise ConflictError("Only draft versions can be deleted.")
    await soft_delete_version(db, version)


async def soft_delete_version(db: AsyncSession, version: CurriculumVersion) -> None:
    """Soft-delete a version of any status with everything in it (its structure, objectives,
    mapping links and assessments). ``delete_draft`` checks the status first; only the removal of
    the demo data (``remove-demo``) deletes a published version."""
    now = datetime.now(UTC)
    module_ids = select(Module.id).where(Module.version_id == version.id)
    rows: list[Objective | LearningEvent | Module | Phase] = []
    rows += await db.scalars(
        select(Objective).where(Objective.version_id == version.id, Objective.deleted_at.is_(None))
    )
    rows += await db.scalars(
        select(LearningEvent).where(
            LearningEvent.module_id.in_(module_ids), LearningEvent.deleted_at.is_(None)
        )
    )
    rows += await db.scalars(
        select(Module).where(Module.version_id == version.id, Module.deleted_at.is_(None))
    )
    rows += await db.scalars(
        select(Phase).where(Phase.version_id == version.id, Phase.deleted_at.is_(None))
    )
    for row in rows:
        row.deleted_at = now
    await soft_delete_links(db, [row.id for row in rows if isinstance(row, Objective)], at=now)
    await soft_delete_assessments(
        db, list(await db.scalars(select(Module.id).where(Module.version_id == version.id))), at=now
    )
    version.deleted_at = now
    await db.flush()


# --- Copy forward -------------------------------------------------------------------


class SkipReason(StrEnum):
    """Why a role assignment is not offered for copying."""

    EXPIRED = "expired"
    ACCOUNT_INACTIVE = "account_inactive"
    ACCOUNT_DELETED = "account_deleted"
    NOT_ALLOWED = "not_allowed"  # the caller may not grant this role


@dataclass(frozen=True)
class RoleCopy:
    """A role assignment at a module or session of the source version."""

    assignment: RoleAssignment
    # Where it is held: "HBIO101 Foundations..." or "HBIO101 · Cells and tissues".
    item: str
    skip_reason: SkipReason | None

    @property
    def copyable(self) -> bool:
        return self.skip_reason is None


@dataclass(frozen=True)
class ForwardPreview:
    """What copying a version forward would create."""

    academic_year: int  # suggested: the year after the programme's latest version
    taken_years: list[int]
    phases: int
    modules: int
    learning_events: int
    objectives: int
    mappings: int
    # Whether the caller may assign roles at the programme (and so sees the list).
    can_copy_roles: bool
    role_assignments: list[RoleCopy]


async def _taken_years(db: AsyncSession, programme_id: uuid.UUID) -> list[int]:
    return sorted(
        await db.scalars(
            select(CurriculumVersion.academic_year).where(
                CurriculumVersion.programme_id == programme_id,
                CurriculumVersion.deleted_at.is_(None),
            )
        )
    )


async def _live_events(db: AsyncSession, module_ids: Collection[uuid.UUID]) -> list[LearningEvent]:
    if not module_ids:
        return []
    return list(
        await db.scalars(
            select(LearningEvent)
            .where(LearningEvent.module_id.in_(module_ids), LearningEvent.deleted_at.is_(None))
            .order_by(LearningEvent.position, LearningEvent.title)
        )
    )


async def _role_copies(
    db: AsyncSession, actor: User | None, version: CurriculumVersion
) -> list[RoleCopy]:
    """The role assignments at the version's live modules and sessions, each with the
    reason it cannot be copied (if any)."""
    modules = {module.id: module for module in await _live_modules(db, version.id)}
    events = {event.id: event for event in await _live_events(db, modules)}
    if not modules:
        return []
    conditions = [
        and_(
            RoleAssignment.scope_type == ScopeType.MODULE,
            RoleAssignment.scope_id.in_(list(modules)),
        )
    ]
    if events:
        conditions.append(
            and_(
                RoleAssignment.scope_type == ScopeType.LEARNING_EVENT,
                RoleAssignment.scope_id.in_(list(events)),
            )
        )
    assignments = list(
        await db.scalars(
            select(RoleAssignment)
            .where(or_(*conditions))
            .options(selectinload(RoleAssignment.role), selectinload(RoleAssignment.user))
            .order_by(RoleAssignment.created_at)
        )
    )
    held = (
        await permissions_at(db, actor, ScopeRef(ScopeType.PROGRAMME, version.programme_id))
        if actor is not None
        else None
    )
    now = datetime.now(UTC)
    copies = []
    for assignment in assignments:
        assert assignment.scope_id is not None
        if assignment.scope_type == ScopeType.MODULE:
            module = modules[assignment.scope_id]
            item = f"{module.code} {module.name}"
        else:
            event = events[assignment.scope_id]
            item = f"{modules[event.module_id].code} · {event.title}"
        reason = None
        if assignment.expires_at is not None and assignment.expires_at <= now:
            reason = SkipReason.EXPIRED
        elif assignment.user.is_deleted:
            reason = SkipReason.ACCOUNT_DELETED
        elif not assignment.user.is_active:
            reason = SkipReason.ACCOUNT_INACTIVE
        elif held is not None and (
            Permission.ROLES_ASSIGN not in held or not role_permissions(assignment.role) <= held
        ):
            reason = SkipReason.NOT_ALLOWED
        copies.append(RoleCopy(assignment, item, reason))
    return copies


async def _may_assign_roles(db: AsyncSession, actor: User, programme_id: uuid.UUID) -> bool:
    held = await permissions_at(db, actor, ScopeRef(ScopeType.PROGRAMME, programme_id))
    return Permission.ROLES_ASSIGN in held


async def forward_preview(
    db: AsyncSession, actor: User, version: CurriculumVersion
) -> ForwardPreview:
    """Counts of what a copy would hold, a suggested year and the role assignments.

    Role assignments (with people's names) are listed only to callers who may assign
    roles at the programme.
    """
    taken = await _taken_years(db, version.programme_id)
    modules = await _live_modules(db, version.id)
    events = await _live_events(db, [module.id for module in modules])
    objective_ids = select(Objective.id).where(
        Objective.version_id == version.id, Objective.deleted_at.is_(None)
    )
    objectives = await db.scalar(select(func.count()).select_from(objective_ids.subquery()))
    mappings = await db.scalar(
        select(func.count(MappingLink.id)).where(
            MappingLink.objective_id.in_(objective_ids), live_link()
        )
    )
    can_copy_roles = await _may_assign_roles(db, actor, version.programme_id)
    return ForwardPreview(
        academic_year=max([version.academic_year, *taken]) + 1,
        taken_years=taken,
        phases=len(await phase_siblings(db, version.id)),
        modules=len(modules),
        learning_events=len(events),
        objectives=int(objectives or 0),
        mappings=int(mappings or 0),
        can_copy_roles=can_copy_roles,
        role_assignments=await _role_copies(db, actor, version) if can_copy_roles else [],
    )


async def _copy_mappings(db: AsyncSession, copies: Copies) -> int:
    """Copy the framework mappings of the copied objectives, with their review state."""
    if not copies.objectives:
        return 0
    links = list(
        await db.scalars(
            select(MappingLink)
            .where(MappingLink.objective_id.in_(list(copies.objectives)), live_link())
            .order_by(MappingLink.created_at)
        )
    )
    for link in links:
        db.add(
            MappingLink(
                objective_id=copies.objectives[link.objective_id].id,
                framework_item_id=link.framework_item_id,
                coverage=link.coverage,
                depth_match=link.depth_match,
                rationale=link.rationale,
                evidence_quote=link.evidence_quote,
                source=link.source,
                confidence=link.confidence,
                status=link.status,
                accept_method=link.accept_method,
                needs_discussion=link.needs_discussion,
                needs_recheck=link.needs_recheck,
                first_reviewer_id=link.first_reviewer_id,
                first_reviewed_at=link.first_reviewed_at,
                first_decision=link.first_decision,
                second_reviewer_id=link.second_reviewer_id,
                second_reviewed_at=link.second_reviewed_at,
                ai_run_id=link.ai_run_id,
                created_by_id=copies.actor_id,
            )
        )
    await db.flush()
    return len(links)


async def copy_forward(
    db: AsyncSession,
    actor: User | None,
    version: CurriculumVersion,
    *,
    academic_year: int,
    role_assignment_ids: Collection[uuid.UUID] = (),
) -> CurriculumVersion:
    """Copy a version, with everything in it, to a new draft for ``academic_year``.

    ``actor`` None is a system action (the demo loader). ``role_assignment_ids`` picks
    which of the preview's copyable role assignments go along.

    Raises:
        ConflictError: If the programme already has a version for that year.
        InvalidRequestError: If a role assignment is not a copyable one of this version.
    """
    if version.deleted_at is not None:
        raise ConflictError("This curriculum version has been deleted.")
    if academic_year in await _taken_years(db, version.programme_id):
        raise ConflictError(f"This programme already has a version for {academic_year}.")
    wanted = set(role_assignment_ids)
    roles: list[RoleCopy] = []
    if wanted:
        if actor is not None and not await _may_assign_roles(db, actor, version.programme_id):
            raise InvalidRequestError("You may not assign roles in this programme.")
        roles = [
            copy for copy in await _role_copies(db, actor, version) if copy.assignment.id in wanted
        ]
        if {copy.assignment.id for copy in roles if copy.copyable} != wanted:
            raise InvalidRequestError(
                "Only current role assignments in this version that you may grant can be copied."
            )

    actor_id = actor.id if actor is not None else None
    new = CurriculumVersion(
        programme_id=version.programme_id,
        academic_year=academic_year,
        status=S.DRAFT,
        based_on_id=version.id,
        created_by_id=actor_id,
    )
    db.add(new)
    await db.flush()

    phases: dict[uuid.UUID, Phase] = {}
    for phase in await phase_siblings(db, version.id):
        phases[phase.id] = Phase(
            version_id=new.id,
            name=phase.name,
            kind=phase.kind,
            external_id=phase.external_id,
            position=phase.position,
            based_on_id=phase.id,
            created_by_id=actor_id,
        )
        db.add(phases[phase.id])
    await db.flush()

    copies = Copies(actor_id, source_version_id=version.id, version_id=new.id)
    for module in await _live_modules(db, version.id):
        new_phase = phases.get(module.phase_id) if module.phase_id else None
        await copy_module_rows(
            db,
            module,
            code=module.code,
            name=module.name,
            # A module whose phase was deleted shows across phases; so does its copy.
            phase_id=new_phase.id if new_phase else None,
            position=module.position,
            copies=copies,
        )
    await copy_children(db, copies)
    await _copy_mappings(db, copies)

    for role in roles:
        assignment = role.assignment
        assert assignment.scope_id is not None
        rows = copies.modules if assignment.scope_type == ScopeType.MODULE else copies.events
        await assign_role(
            db,
            actor,
            user=assignment.user,
            role=assignment.role,
            scope=ScopeRef(ScopeType(assignment.scope_type), rows[assignment.scope_id].id),
            expires_at=assignment.expires_at,
        )
    return new
