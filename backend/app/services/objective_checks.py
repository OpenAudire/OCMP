"""Running the objective quality checker against the database (ADR 033).

The rules themselves are pure (``app.services.objective_quality``). This module loads the
taxonomy levels and their verbs, and for the bulk check collects the objectives of one
version that the user may see, with the context the rules need.
"""

import uuid
from collections import Counter
from dataclasses import dataclass, field, replace

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.ai import privacy
from app.core.permissions import Permission, ScopeType
from app.models import (
    LearningEvent,
    Module,
    Objective,
    ObjectiveLink,
    TaxonomyScale,
)
from app.models.curriculum import ObjectiveLevel, ObjectiveStatus
from app.services.authorization import AuthorizationError
from app.services.curriculum_edit import is_editable
from app.services.curriculum_read import CurriculumAccess, VisibleVersion
from app.services.objective_duplicates import pairs_among
from app.services.objective_quality import (
    CheckContext,
    CheckResult,
    Finding,
    LevelVerbs,
    check_objective,
)
from app.services.policies import quality_policy_for_version


async def level_verbs(db: AsyncSession) -> list[LevelVerbs]:
    """Every taxonomy level with its verb list, scales in name order."""
    scales = await db.scalars(
        select(TaxonomyScale)
        .options(selectinload(TaxonomyScale.levels))
        .order_by(TaxonomyScale.name)
    )
    found: list[LevelVerbs] = []
    for index, scale in enumerate(scales):
        found.extend(
            LevelVerbs(
                level_id=level.id,
                level_name=level.name,
                scale_key=scale.key,
                scale_name=scale.name,
                scale_position=index,
                level_position=level.position,
                verbs=tuple(level.verbs),
            )
            for level in scale.levels
        )
    return found


async def check_text(
    db: AsyncSession,
    text: str,
    context: CheckContext,
) -> CheckResult:
    """Check wording typed in the editor; nothing is saved."""
    return check_objective(text, context, await level_verbs(db))


def may_use_checker(access: CurriculumAccess) -> bool:
    """Whether the user holds ``objectives.edit`` anywhere (the bulk check is for editors)."""
    held = [access.instance, *access.scoped.values()]
    return any(Permission.OBJECTIVES_EDIT in permissions for permissions in held)


@dataclass(frozen=True)
class NearDuplicate:
    """Another objective of the same version and level that reads almost the same."""

    objective: Objective
    module: Module | None
    event: LearningEvent | None
    similarity: float


@dataclass(frozen=True)
class CheckedObjective:
    objective: Objective
    module: Module | None
    event: LearningEvent | None
    result: CheckResult
    can_edit: bool
    near_duplicates: list[NearDuplicate] = field(default_factory=list)


Row = tuple[Objective, Module | None, LearningEvent | None]


async def visible_objectives(db: AsyncSession, visible: VisibleVersion) -> list[Row]:
    """The live, non-retired objectives of a version that the user may see, in curriculum
    order (ADR 027). Retired objectives are no longer taught."""
    version, view = visible.version, visible.view
    module_id = func.coalesce(Objective.module_id, LearningEvent.module_id)
    rows = (
        await db.execute(
            select(Objective, Module, LearningEvent)
            .outerjoin(LearningEvent, LearningEvent.id == Objective.learning_event_id)
            .outerjoin(Module, Module.id == module_id)
            .where(
                Objective.version_id == version.id,
                Objective.deleted_at.is_(None),
                Objective.status != ObjectiveStatus.RETIRED,
            )
            .order_by(
                Objective.level != ObjectiveLevel.PROGRAMME,
                Module.position,
                Module.code,
                Objective.level != ObjectiveLevel.MODULE,
                LearningEvent.position,
                Objective.position,
                Objective.created_at,
            )
        )
    ).all()

    def shown(objective: Objective, module: Module | None, event: LearningEvent | None) -> bool:
        if objective.level == ObjectiveLevel.PROGRAMME:
            return view.full
        if module is None or module.deleted_at is not None:
            return False
        if objective.level == ObjectiveLevel.MODULE:
            return view.shows_module(module.id)
        return (
            event is not None and event.deleted_at is None and view.shows_event(module.id, event.id)
        )

    return [(o, m, e) for o, m, e in rows if shown(o, m, e)]


async def near_duplicates_among(
    db: AsyncSession, version_id: uuid.UUID, chosen: list[Row]
) -> dict[uuid.UUID, list[NearDuplicate]]:
    """Stored near-duplicate pairs among the objectives the user may see, by objective.

    A pair is reported to both sides and only when the user may see both (ADR 027). The
    threshold is the institution's (``settings["quality"]``). Most similar first."""
    policy = await quality_policy_for_version(db, version_id)
    pairs = await pairs_among(db, [o.id for o, _, _ in chosen], policy.near_duplicate_min_percent)
    by_id = {o.id: (o, m, e) for o, m, e in chosen}
    found: dict[uuid.UUID, list[NearDuplicate]] = {}
    for pair in pairs:
        first, second = by_id[pair.objective_id], by_id[pair.other_id]
        found.setdefault(first[0].id, []).append(NearDuplicate(*second, pair.similarity))
        found.setdefault(second[0].id, []).append(NearDuplicate(*first, pair.similarity))
    for matches in found.values():
        matches.sort(key=lambda match: -match.similarity)
    return found


def duplicate_finding(match: NearDuplicate) -> Finding:
    where = match.module.code if match.module is not None else ""
    if match.event is not None:
        where = f"{where} {match.event.title}".strip()
    return Finding(
        "near_duplicate",
        {"percent": str(int(match.similarity * 100)), "where": where},
    )


async def check_version(
    db: AsyncSession, visible: VisibleVersion, *, near_duplicates: bool = False
) -> list[CheckedObjective]:
    """Check the live objectives of a version that the user sees, in curriculum order.

    Besides the wording rules, the bulk check reports wording that the privacy detectors
    flag, so it gets fixed, and, when ``near_duplicates`` is true (embeddings are on),
    near-duplicates from the stored pairs (ADR 044).

    Objectives of items the user cannot see are left out (ADR 027)."""
    if not may_use_checker(visible.access):
        raise AuthorizationError("You do not have permission to check objectives.")
    version, access = visible.version, visible.access
    chosen = await visible_objectives(db, visible)
    duplicates = await near_duplicates_among(db, version.id, chosen) if near_duplicates else {}
    known_names = await privacy.load_known_names(db)
    parents: set[uuid.UUID] = set()
    if chosen:
        parent = Objective.__table__.alias("parent")
        linked = await db.scalars(
            select(ObjectiveLink.child_id)
            .join(parent, parent.c.id == ObjectiveLink.parent_id)
            .where(
                ObjectiveLink.child_id.in_([o.id for o, _, _ in chosen]),
                parent.c.deleted_at.is_(None),
            )
        )
        parents = set(linked)

    levels = await level_verbs(db)
    programme_permissions = access.for_programme(visible.programme)
    editable = is_editable(version)
    checked: list[CheckedObjective] = []
    for objective, module, event in chosen:
        held = programme_permissions
        if module is not None:
            held = held | access.at(ScopeType.MODULE, module.id)
        if event is not None:
            held = held | access.at(ScopeType.LEARNING_EVENT, event.id)
        result = check_objective(
            objective.text,
            CheckContext(
                level=objective.level,
                domain=objective.domain,
                taxonomy_level_id=objective.taxonomy_level_id,
                has_parent_links=objective.id in parents,
            ),
            levels,
        )
        extra: list[Finding] = []
        matches = duplicates.get(objective.id, [])
        if matches:
            extra.append(duplicate_finding(matches[0]))
        kinds = Counter(f.category.value for f in privacy.detect(objective.text, known_names))
        if kinds:
            extra.append(
                Finding("possible_personal_information", {"kinds": ", ".join(sorted(kinds))})
            )
        if extra:
            result = replace(result, findings=[*result.findings, *extra])
        checked.append(
            CheckedObjective(
                objective,
                module,
                event,
                result,
                can_edit=editable and Permission.OBJECTIVES_EDIT in held,
                near_duplicates=matches,
            )
        )
    return checked
