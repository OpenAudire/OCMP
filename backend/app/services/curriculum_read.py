"""Reading the curriculum: what a user may see, and the structure of a version.

Visibility follows the scoped permissions (ADR 012), computed in bulk from the
user's role assignments instead of one lineage lookup per row:

- ``curriculum.view`` at a scope shows every version there, drafts included;
  ``curriculum.view_published`` shows only published versions.
- A role at programme level or above shows the whole version. A role at a
  module shows that module with all its sessions; a role at a learning event
  shows only that session, under its module as context. Narrower roles never
  reveal anything above them except the names needed to place them in the tree.
- Soft-deleted rows, and programmes of a deleted faculty, are not shown.

Callers turn "not visible" into 404, so the API does not reveal what exists.
"""

import uuid
from collections import defaultdict
from dataclasses import dataclass, field

from sqlalchemy import ColumnElement, Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.permissions import Permission, ScopeType
from app.models import (
    CurriculumVersion,
    Faculty,
    LearningEvent,
    Module,
    Objective,
    ObjectiveLink,
    Phase,
    Programme,
    TagValue,
    User,
)
from app.models.curriculum import ObjectiveLevel, VersionStatus
from app.services.authorization import role_permissions, user_assignments
from app.services.curriculum_edit import is_editable

Permissions = frozenset[Permission]
_NONE: Permissions = frozenset()


def _sees(permissions: Permissions, status: VersionStatus) -> bool:
    """Whether these permissions show a version with this status."""
    if Permission.CURRICULUM_VIEW in permissions:
        return True
    return Permission.CURRICULUM_VIEW_PUBLISHED in permissions and (
        status == VersionStatus.PUBLISHED
    )


@dataclass(frozen=True)
class CurriculumAccess:
    """A user's permissions per scope, gathered once per request."""

    instance: Permissions = _NONE
    scoped: dict[tuple[ScopeType, uuid.UUID], Permissions] = field(default_factory=dict)

    def at(self, scope_type: ScopeType, scope_id: uuid.UUID) -> Permissions:
        return self.scoped.get((scope_type, scope_id), _NONE)

    def ids(self, scope_type: ScopeType) -> set[uuid.UUID]:
        return {scope_id for kind, scope_id in self.scoped if kind == scope_type}

    def for_programme(self, programme: Programme) -> Permissions:
        return (
            self.instance
            | self.at(ScopeType.FACULTY, programme.faculty_id)
            | self.at(ScopeType.PROGRAMME, programme.id)
        )


async def curriculum_access(db: AsyncSession, user: User) -> CurriculumAccess:
    """Collect the user's current permissions by scope."""
    if not user.is_active or user.is_deleted:
        return CurriculumAccess()
    instance: set[Permission] = set()
    scoped: dict[tuple[ScopeType, uuid.UUID], set[Permission]] = defaultdict(set)
    for assignment in await user_assignments(db, user.id):
        permissions = role_permissions(assignment.role)
        if assignment.scope_id is None:
            instance |= permissions
        else:
            scoped[(ScopeType(assignment.scope_type), assignment.scope_id)] |= permissions
    return CurriculumAccess(
        instance=frozenset(instance),
        scoped={key: frozenset(value) for key, value in scoped.items()},
    )


@dataclass(frozen=True)
class VersionView:
    """What of one version a user sees.

    ``full`` shows everything. Otherwise ``modules`` are shown whole, and
    ``events`` maps further modules (shown as context only) to their visible sessions.
    """

    full: bool
    modules: frozenset[uuid.UUID] = frozenset()
    events: dict[uuid.UUID, frozenset[uuid.UUID]] = field(default_factory=dict)

    @property
    def visible(self) -> bool:
        return self.full or bool(self.modules) or bool(self.events)

    def shows_module(self, module_id: uuid.UUID) -> bool:
        """Whether the module itself (details and outcomes) is visible."""
        return self.full or module_id in self.modules

    def shows_event(self, module_id: uuid.UUID, event_id: uuid.UUID) -> bool:
        return self.shows_module(module_id) or event_id in self.events.get(module_id, ())


@dataclass
class _NarrowScopes:
    """Module and event scopes the user holds, located in their versions."""

    # version id -> module ids with a role at the module
    modules: dict[uuid.UUID, set[uuid.UUID]] = field(default_factory=lambda: defaultdict(set))
    # version id -> (module id, event id) with a role at the event
    events: dict[uuid.UUID, set[tuple[uuid.UUID, uuid.UUID]]] = field(
        default_factory=lambda: defaultdict(set)
    )


async def _narrow_scopes(
    db: AsyncSession, access: CurriculumAccess, version_ids: set[uuid.UUID] | None = None
) -> _NarrowScopes:
    found = _NarrowScopes()
    module_ids = access.ids(ScopeType.MODULE)
    event_ids = access.ids(ScopeType.LEARNING_EVENT)
    if module_ids:
        query = select(Module.id, Module.version_id).where(
            Module.id.in_(module_ids), Module.deleted_at.is_(None)
        )
        if version_ids is not None:
            query = query.where(Module.version_id.in_(version_ids))
        for module_id, version_id in await db.execute(query):
            found.modules[version_id].add(module_id)
    if event_ids:
        event_query = (
            select(LearningEvent.id, Module.id, Module.version_id)
            .join(Module, Module.id == LearningEvent.module_id)
            .where(
                LearningEvent.id.in_(event_ids),
                LearningEvent.deleted_at.is_(None),
                Module.deleted_at.is_(None),
            )
        )
        if version_ids is not None:
            event_query = event_query.where(Module.version_id.in_(version_ids))
        for event_id, module_id, version_id in await db.execute(event_query):
            found.events[version_id].add((module_id, event_id))
    return found


def _version_view(
    access: CurriculumAccess,
    programme_permissions: Permissions,
    version: CurriculumVersion,
    narrow: _NarrowScopes,
) -> VersionView:
    if _sees(programme_permissions, version.status):
        return VersionView(full=True)
    modules = frozenset(
        module_id
        for module_id in narrow.modules.get(version.id, ())
        if _sees(programme_permissions | access.at(ScopeType.MODULE, module_id), version.status)
    )
    events: dict[uuid.UUID, set[uuid.UUID]] = defaultdict(set)
    for module_id, event_id in narrow.events.get(version.id, ()):
        if module_id in modules:
            continue
        held = (
            programme_permissions
            | access.at(ScopeType.MODULE, module_id)
            | access.at(ScopeType.LEARNING_EVENT, event_id)
        )
        if _sees(held, version.status):
            events[module_id].add(event_id)
    return VersionView(
        full=False,
        modules=modules,
        events={module_id: frozenset(ids) for module_id, ids in events.items()},
    )


def _live_programmes() -> Select[Programme]:
    return (
        select(Programme)
        .join(Faculty, Faculty.id == Programme.faculty_id)
        .where(Programme.deleted_at.is_(None), Faculty.deleted_at.is_(None))
        .options(selectinload(Programme.faculty), selectinload(Programme.versions))
    )


@dataclass(frozen=True)
class VisibleProgramme:
    programme: Programme
    # Newest academic year first.
    versions: list[CurriculumVersion]


async def visible_programmes(db: AsyncSession, access: CurriculumAccess) -> list[VisibleProgramme]:
    """Programmes with at least one visible version, by name, with those versions."""
    result = await db.execute(_live_programmes().order_by(Programme.name, Programme.code))
    programmes = list(result.scalars())
    narrow = await _narrow_scopes(db, access)
    visible = []
    for programme in programmes:
        permissions = access.for_programme(programme)
        versions = [
            version
            for version in sorted(programme.versions, key=lambda v: -v.academic_year)
            if version.deleted_at is None
            and _version_view(access, permissions, version, narrow).visible
        ]
        if versions:
            visible.append(VisibleProgramme(programme, versions))
    return visible


async def visible_programme(
    db: AsyncSession, access: CurriculumAccess, programme_id: uuid.UUID
) -> VisibleProgramme | None:
    """One programme, if the user sees at least one of its versions."""
    result = await db.execute(_live_programmes().where(Programme.id == programme_id))
    programme = result.scalar_one_or_none()
    if programme is None:
        return None
    permissions = access.for_programme(programme)
    live = [v for v in programme.versions if v.deleted_at is None]
    narrow = await _narrow_scopes(db, access, {v.id for v in live})
    versions = [
        version
        for version in sorted(live, key=lambda v: -v.academic_year)
        if _version_view(access, permissions, version, narrow).visible
    ]
    return VisibleProgramme(programme, versions) if versions else None


@dataclass(frozen=True)
class VisibleVersion:
    version: CurriculumVersion
    programme: Programme
    view: VersionView
    access: CurriculumAccess


async def visible_version(
    db: AsyncSession, access: CurriculumAccess, version_id: uuid.UUID
) -> VisibleVersion | None:
    """A live version and what of it the user sees, or None if nothing."""
    result = await db.execute(
        select(CurriculumVersion, Programme)
        .join(Programme, Programme.id == CurriculumVersion.programme_id)
        .join(Faculty, Faculty.id == Programme.faculty_id)
        .where(
            CurriculumVersion.id == version_id,
            CurriculumVersion.deleted_at.is_(None),
            Programme.deleted_at.is_(None),
            Faculty.deleted_at.is_(None),
        )
    )
    row = result.one_or_none()
    if row is None:
        return None
    version, programme = row
    narrow = await _narrow_scopes(db, access, {version.id})
    view = _version_view(access, access.for_programme(programme), version, narrow)
    return VisibleVersion(version, programme, view, access) if view.visible else None


# --- Structure ----------------------------------------------------------------------


@dataclass
class EventNode:
    event: LearningEvent
    format_label: str | None
    objective_count: int
    # Whether the user may edit this session (curriculum.edit at it or above).
    can_edit: bool = False


@dataclass
class ModuleNode:
    module: Module
    # Only the module's name and code are shown; the user sees some of its sessions.
    context_only: bool
    objective_count: int
    events: list[EventNode] = field(default_factory=list)
    # Whether the user may edit the module and add or remove its sessions.
    can_edit: bool = False


@dataclass
class PhaseNode:
    phase: Phase
    modules: list[ModuleNode] = field(default_factory=list)


@dataclass
class Structure:
    visible: VisibleVersion
    phases: list[PhaseNode]
    # Longitudinal modules, and modules whose phase was deleted.
    modules_without_phase: list[ModuleNode]
    # Programme outcomes; None when the user does not see the whole version.
    outcome_count: int | None
    # Whether the user may add, change and remove phases and modules.
    can_edit: bool = False
    # Whether the user may publish, unpublish, archive or unarchive the version.
    can_change_status: bool = False
    # Whether the user may copy the version forward (and delete it while a draft).
    can_copy_forward: bool = False


async def _objective_counts(
    db: AsyncSession, version_id: uuid.UUID
) -> dict[tuple[ObjectiveLevel, uuid.UUID | None], int]:
    owner = func.coalesce(Objective.learning_event_id, Objective.module_id)
    result = await db.execute(
        select(Objective.level, owner, func.count())
        .where(Objective.version_id == version_id, Objective.deleted_at.is_(None))
        .group_by(Objective.level, owner)
    )
    return {(ObjectiveLevel(level), owner_id): count for level, owner_id, count in result}


async def version_structure(db: AsyncSession, visible: VisibleVersion) -> Structure:
    """The phases, modules and sessions of a version that the user sees, in order."""
    version, view = visible.version, visible.view
    phases = list(
        await db.scalars(
            select(Phase)
            .where(Phase.version_id == version.id, Phase.deleted_at.is_(None))
            .order_by(Phase.position, Phase.name)
        )
    )
    modules = list(
        await db.scalars(
            select(Module)
            .where(Module.version_id == version.id, Module.deleted_at.is_(None))
            .order_by(Module.position, Module.code)
        )
    )
    event_rows = await db.execute(
        select(LearningEvent, TagValue.label)
        .join(Module, Module.id == LearningEvent.module_id)
        .outerjoin(
            TagValue,
            (TagValue.id == LearningEvent.format_value_id) & TagValue.deleted_at.is_(None),
        )
        .where(Module.version_id == version.id, LearningEvent.deleted_at.is_(None))
        .order_by(LearningEvent.position, LearningEvent.title)
    )
    counts = await _objective_counts(db, version.id)
    access = visible.access
    editable = is_editable(version)
    programme_permissions = access.for_programme(visible.programme)

    def edits(*held: Permissions) -> bool:
        return editable and any(Permission.CURRICULUM_EDIT in p for p in held)

    nodes: dict[uuid.UUID, ModuleNode] = {}
    for module in modules:
        if view.shows_module(module.id) or module.id in view.events:
            nodes[module.id] = ModuleNode(
                module=module,
                context_only=not view.shows_module(module.id),
                objective_count=counts.get((ObjectiveLevel.MODULE, module.id), 0),
                can_edit=view.shows_module(module.id)
                and edits(programme_permissions, access.at(ScopeType.MODULE, module.id)),
            )
    for event, format_label in event_rows:
        node = nodes.get(event.module_id)
        if node is not None and view.shows_event(event.module_id, event.id):
            node.events.append(
                EventNode(
                    event=event,
                    format_label=format_label,
                    objective_count=counts.get((ObjectiveLevel.LEARNING_EVENT, event.id), 0),
                    can_edit=edits(
                        programme_permissions,
                        access.at(ScopeType.MODULE, event.module_id),
                        access.at(ScopeType.LEARNING_EVENT, event.id),
                    ),
                )
            )

    phase_nodes = {phase.id: PhaseNode(phase) for phase in phases}
    without_phase: list[ModuleNode] = []
    for module_node in nodes.values():
        phase_id = module_node.module.phase_id
        if phase_id is not None and phase_id in phase_nodes:
            phase_nodes[phase_id].modules.append(module_node)
        else:
            without_phase.append(module_node)
    return Structure(
        visible=visible,
        # Narrower roles see only the phases that hold their modules.
        phases=[p for p in phase_nodes.values() if view.full or p.modules],
        modules_without_phase=without_phase,
        outcome_count=counts.get((ObjectiveLevel.PROGRAMME, None), 0) if view.full else None,
        can_edit=edits(programme_permissions),
        can_change_status=view.full and Permission.CURRICULUM_PUBLISH in programme_permissions,
        can_copy_forward=view.full and Permission.CURRICULUM_EDIT in programme_permissions,
    )


# --- Details ------------------------------------------------------------------------


@dataclass
class ObjectiveWithLinks:
    objective: Objective
    # Broader objectives this one contributes to (live ones only).
    parent_ids: list[uuid.UUID]


async def _objectives(
    db: AsyncSession, *conditions: ColumnElement[bool]
) -> list[ObjectiveWithLinks]:
    objectives = list(
        await db.scalars(
            select(Objective)
            .where(Objective.deleted_at.is_(None), *conditions)
            .order_by(Objective.position, Objective.created_at)
        )
    )
    parents: dict[uuid.UUID, list[uuid.UUID]] = defaultdict(list)
    if objectives:
        parent = Objective.__table__.alias("parent")
        links = await db.execute(
            select(ObjectiveLink.child_id, ObjectiveLink.parent_id)
            .join(parent, parent.c.id == ObjectiveLink.parent_id)
            .where(
                ObjectiveLink.child_id.in_([o.id for o in objectives]),
                parent.c.deleted_at.is_(None),
            )
            .order_by(parent.c.position)
        )
        for child_id, parent_id in links:
            parents[child_id].append(parent_id)
    return [ObjectiveWithLinks(o, parents[o.id]) for o in objectives]


async def programme_outcomes(db: AsyncSession, version_id: uuid.UUID) -> list[ObjectiveWithLinks]:
    """The version's programme-level outcomes, in order."""
    return await _objectives(
        db, Objective.version_id == version_id, Objective.level == ObjectiveLevel.PROGRAMME
    )


@dataclass(frozen=True)
class ModuleDetail:
    module: Module
    version: VisibleVersion
    contact_minutes: int
    self_study_minutes: int
    event_count: int
    outcomes: list[ObjectiveWithLinks]


async def module_detail(
    db: AsyncSession, access: CurriculumAccess, module_id: uuid.UUID
) -> ModuleDetail | None:
    """A module with its totals and outcomes, if the user sees the module itself."""
    module = await db.scalar(
        select(Module).where(Module.id == module_id, Module.deleted_at.is_(None))
    )
    if module is None:
        return None
    visible = await visible_version(db, access, module.version_id)
    if visible is None or not visible.view.shows_module(module.id):
        return None
    contact, self_study, events = (
        await db.execute(
            select(
                func.coalesce(func.sum(LearningEvent.contact_minutes), 0),
                func.coalesce(func.sum(LearningEvent.self_study_minutes), 0),
                func.count(LearningEvent.id),
            ).where(LearningEvent.module_id == module.id, LearningEvent.deleted_at.is_(None))
        )
    ).one()
    outcomes = await _objectives(
        db, Objective.module_id == module.id, Objective.level == ObjectiveLevel.MODULE
    )
    return ModuleDetail(module, visible, int(contact), int(self_study), int(events), outcomes)


@dataclass(frozen=True)
class EventDetail:
    event: LearningEvent
    module: Module
    version: VisibleVersion
    format_label: str | None
    objectives: list[ObjectiveWithLinks]


async def event_detail(
    db: AsyncSession, access: CurriculumAccess, event_id: uuid.UUID
) -> EventDetail | None:
    """A session with its objectives, if the user sees it."""
    row = (
        await db.execute(
            select(LearningEvent, Module, TagValue.label)
            .join(Module, Module.id == LearningEvent.module_id)
            .outerjoin(
                TagValue,
                (TagValue.id == LearningEvent.format_value_id) & TagValue.deleted_at.is_(None),
            )
            .where(
                LearningEvent.id == event_id,
                LearningEvent.deleted_at.is_(None),
                Module.deleted_at.is_(None),
            )
        )
    ).one_or_none()
    if row is None:
        return None
    event, module, format_label = row
    visible = await visible_version(db, access, module.version_id)
    if visible is None or not visible.view.shows_event(module.id, event.id):
        return None
    objectives = await _objectives(
        db,
        Objective.learning_event_id == event.id,
        Objective.level == ObjectiveLevel.LEARNING_EVENT,
    )
    return EventDetail(event, module, visible, format_label, objectives)
