"""The redundancy and traceability reports (Slice 1.23, ADR 052) as report documents.

* **Redundancy**: framework items taught in unusually many sessions, and near-duplicate
  objectives in different modules.
* **Traceability**: each programme outcome down through the module outcomes and session
  objectives that contribute to it, to the framework items they are mapped to.

Both read only what the person's roles show (ADR 027) and only accepted mapping links.
"""

from __future__ import annotations

import statistics
import uuid
from collections import defaultdict
from datetime import UTC, datetime

from sqlalchemy import select

from app.models import (
    Framework,
    FrameworkItem,
    LearningEvent,
    MappingLink,
    Module,
    ObjectiveLink,
)
from app.models.curriculum import ObjectiveLevel
from app.models.mapping import MappingStatus
from app.services.mapping_live import live_link
from app.services.objective_checks import near_duplicates_among, visible_objectives
from app.services.report_context import ReportContext, common_about
from app.services.report_export import Column, Kind, ReportDoc, Section

# An item is "taught in unusually many sessions" from at least this many, and from the average plus
# this many standard deviations when there are enough items to say what usual is.
REDUNDANCY_MIN_SESSIONS = 4
REDUNDANCY_SPREAD = 1.5
REDUNDANCY_MIN_ITEMS_FOR_SPREAD = 5
SESSIONS_LISTED = 8
TRACE_MAX_ROWS = 5000
LEVEL_NAMES = {
    "programme": "Programme outcome",
    "module": "Module outcome",
    "learning_event": "Session",
}


def _now() -> datetime:
    return datetime.now(UTC)


def unusual_threshold(counts: list[int]) -> float:
    """The number of sessions from which a framework item counts as taught in unusually many: at
    least ``REDUNDANCY_MIN_SESSIONS``, and the average plus ``REDUNDANCY_SPREAD`` standard
    deviations when there are enough items to say what the average is."""
    if len(counts) >= REDUNDANCY_MIN_ITEMS_FOR_SPREAD:
        spread = statistics.mean(counts) + REDUNDANCY_SPREAD * statistics.pstdev(counts)
        return max(float(REDUNDANCY_MIN_SESSIONS), spread)
    return float(REDUNDANCY_MIN_SESSIONS)


def _where(module: Module | None, event: LearningEvent | None) -> str:
    code = module.code if module is not None else ""
    return f"{code} {event.title}".strip() if event is not None else code


async def build_redundancy(ctx: ReportContext) -> ReportDoc:
    framework = await ctx.framework()
    made = _now()
    chosen = await visible_objectives(ctx.db, ctx.visible)
    by_id = {o.id: (o, m, e) for o, m, e in chosen}

    # --- framework items taught in many sessions ---
    rows = await ctx.db.execute(
        select(MappingLink.framework_item_id, MappingLink.objective_id)
        .join(FrameworkItem, FrameworkItem.id == MappingLink.framework_item_id)
        .where(
            FrameworkItem.framework_id == framework.id,
            MappingLink.status == MappingStatus.ACCEPTED,
            MappingLink.coverage >= 1,
            MappingLink.objective_id.in_(list(by_id) or [uuid.uuid4()]),
            live_link(),
        )
    )
    sessions: dict[uuid.UUID, dict[uuid.UUID, tuple[Module | None, LearningEvent]]] = defaultdict(
        dict
    )
    modules: dict[uuid.UUID, set[uuid.UUID]] = defaultdict(set)
    for item_id, objective_id in rows:
        objective, module, event = by_id[objective_id]
        if module is not None:
            modules[item_id].add(module.id)
        if event is not None:
            sessions[item_id][event.id] = (module, event)
    counts = {item_id: len(found) for item_id, found in sessions.items()}
    threshold = unusual_threshold(list(counts.values()))
    items = {
        i.id: i
        for i in await ctx.db.scalars(
            select(FrameworkItem).where(FrameworkItem.framework_id == framework.id)
        )
    }
    flagged = sorted(
        (item_id for item_id, n in counts.items() if n >= threshold),
        key=lambda item_id: (-counts[item_id], items[item_id].code),
    )
    taught = Section(
        "Items taught in many sessions",
        [
            Column("Code"),
            Column("Item"),
            Column("Sessions", Kind.INTEGER),
            Column("Modules", Kind.INTEGER),
            Column("The sessions"),
        ],
        [],
        note=(
            f"Framework items that accepted mapping links tie to at least {threshold:.1f} sessions "
            f"(the larger of {REDUNDANCY_MIN_SESSIONS} and, with {REDUNDANCY_MIN_ITEMS_FOR_SPREAD} "
            f"or more items taught, the average plus {REDUNDANCY_SPREAD} standard deviations). "
            f"{len(counts)} items are taught in at least one session. Many sessions is not "
            "necessarily too many: it may be a thread, or it may be overlap to look at."
        ),
    )
    for item_id in flagged:
        found = sorted(
            sessions[item_id].values(),
            key=lambda pair: (pair[0].code if pair[0] else "", pair[1].week or 0, pair[1].position),
        )
        listed = "; ".join(_where(m, e) for m, e in found[:SESSIONS_LISTED])
        if len(found) > SESSIONS_LISTED:
            listed += f"; and {len(found) - SESSIONS_LISTED} more"
        taught.rows.append(
            [
                items[item_id].code,
                items[item_id].title,
                counts[item_id],
                len(modules[item_id]),
                listed,
            ]
        )

    # --- near-duplicate objectives in different modules ---
    found_pairs = await near_duplicates_among(ctx.db, ctx.visible.version.id, chosen)
    seen: set[frozenset[uuid.UUID]] = set()
    duplicates = Section(
        "Near-duplicate objectives in different modules",
        [
            Column("Similarity", Kind.PERCENT),
            Column("First: where"),
            Column("First: objective"),
            Column("Second: where"),
            Column("Second: objective"),
        ],
        [],
        note=(
            "Pairs of objectives of the same level whose wording is close (the institution's "
            "near-duplicate threshold) and that sit in different modules. They come from the "
            "stored similarities: if the embeddings service is off or has not been run "
            "(embed-all), none are found."
        ),
    )
    ordered = sorted(
        (
            (match.similarity, objective, match)
            for objective_id, matches in found_pairs.items()
            for match in matches
            for objective in [by_id[objective_id][0]]
        ),
        key=lambda t: -t[0],
    )
    for similarity, objective, match in ordered:
        key = frozenset({objective.id, match.objective.id})
        if key in seen:
            continue
        seen.add(key)
        _, module, event = by_id[objective.id]
        if module is None or match.module is None or module.id == match.module.id:
            continue
        duplicates.rows.append(
            [
                similarity,
                _where(module, event),
                objective.text,
                _where(match.module, match.event),
                match.objective.text,
            ]
        )

    about = [
        ("Report", "Redundancy report"),
        (
            "Method",
            "Sessions per framework item, from accepted mapping links; and stored near-duplicate "
            "pairs across modules.",
        ),
        ("Framework", f"{framework.name} ({framework.version_label})"),
        *common_about(ctx.visible, made.strftime("%Y-%m-%d %H:%M UTC"), not ctx.visible.view.full),
    ]
    return ReportDoc(
        key="redundancy",
        title="Redundancy report",
        about=about,
        method="Sessions per framework item and near-duplicate objectives",
        made_on=made,
        sections=[taught, duplicates],
    )


async def build_traceability(ctx: ReportContext) -> ReportDoc:
    made = _now()
    framework: Framework | None = await ctx.optional_framework()
    chosen = await visible_objectives(ctx.db, ctx.visible)
    by_id = {o.id: (o, m, e) for o, m, e in chosen}
    ids = list(by_id) or [uuid.uuid4()]

    parents: dict[uuid.UUID, list[uuid.UUID]] = defaultdict(list)
    children: dict[uuid.UUID, list[uuid.UUID]] = defaultdict(list)
    for child_id, parent_id in await ctx.db.execute(
        select(ObjectiveLink.child_id, ObjectiveLink.parent_id).where(
            ObjectiveLink.child_id.in_(ids), ObjectiveLink.parent_id.in_(ids)
        )
    ):
        parents[child_id].append(parent_id)
        children[parent_id].append(child_id)

    query = (
        select(MappingLink.objective_id, FrameworkItem.code, Framework.name)
        .join(FrameworkItem, FrameworkItem.id == MappingLink.framework_item_id)
        .join(Framework, Framework.id == FrameworkItem.framework_id)
        .where(
            MappingLink.status == MappingStatus.ACCEPTED,
            MappingLink.coverage >= 1,
            MappingLink.objective_id.in_(ids),
            live_link(),
        )
        .order_by(Framework.name, FrameworkItem.code)
    )
    if framework is not None:
        query = query.where(FrameworkItem.framework_id == framework.id)
    mapped: dict[uuid.UUID, list[str]] = defaultdict(list)
    many_frameworks = framework is None
    for objective_id, code, name in await ctx.db.execute(query):
        mapped[objective_id].append(f"{name}: {code}" if many_frameworks else code)

    def items_of(objective_id: uuid.UUID) -> str:
        return ", ".join(dict.fromkeys(mapped.get(objective_id, [])))

    def where(objective_id: uuid.UUID) -> str:
        _, module, event = by_id[objective_id]
        return _where(module, event)

    columns = [
        Column("Programme outcome"),
        Column("Module outcome"),
        Column("Module"),
        Column("Session objective"),
        Column("Session"),
        Column("Mapped to"),
    ]
    traced = Section(
        "From programme outcome to framework item",
        columns,
        [],
        note=(
            "Each row follows the upward links of the curriculum from a programme outcome down "
            "to the module outcomes and session objectives that contribute to it. 'Mapped to' "
            "lists the framework items the last objective of the row is accepted for"
            + (f" in {framework.name}." if framework else " (all frameworks).")
        ),
    )
    covered: set[uuid.UUID] = set()
    capped = False

    def add(row: list[object], *objective_ids: uuid.UUID) -> None:
        nonlocal capped
        if len(traced.rows) >= TRACE_MAX_ROWS:
            capped = True
            return
        covered.update(objective_ids)
        traced.rows.append(row)  # type: ignore[arg-type]

    def level_of(objective_id: uuid.UUID) -> ObjectiveLevel:
        return by_id[objective_id][0].level

    programme = [o for o, _, _ in chosen if o.level is ObjectiveLevel.PROGRAMME]
    for outcome in programme:
        below = [c for c in children.get(outcome.id, []) if c in by_id]
        modules_below = [c for c in below if level_of(c) is ObjectiveLevel.MODULE]
        sessions_direct = [c for c in below if level_of(c) is ObjectiveLevel.LEARNING_EVENT]
        if not below:
            add(
                [
                    outcome.text,
                    None,
                    None,
                    None,
                    None,
                    items_of(outcome.id) or "nothing contributes",
                ],
                outcome.id,
            )
        for module_outcome in modules_below:
            sessions = [
                c
                for c in children.get(module_outcome, [])
                if c in by_id and level_of(c) is ObjectiveLevel.LEARNING_EVENT
            ]
            module_text = by_id[module_outcome][0].text
            if not sessions:
                add(
                    [
                        outcome.text,
                        module_text,
                        where(module_outcome),
                        None,
                        None,
                        items_of(module_outcome),
                    ],
                    outcome.id,
                    module_outcome,
                )
            for session in sessions:
                add(
                    [
                        outcome.text,
                        module_text,
                        where(module_outcome),
                        by_id[session][0].text,
                        where(session),
                        items_of(session),
                    ],
                    outcome.id,
                    module_outcome,
                    session,
                )
        for session in sessions_direct:
            add(
                [
                    outcome.text,
                    None,
                    None,
                    by_id[session][0].text,
                    where(session),
                    items_of(session),
                ],
                outcome.id,
                session,
            )
    if capped:
        traced.note += f" Cut at {TRACE_MAX_ROWS} rows."

    loose = Section(
        "Not linked upward to a programme outcome you can see",
        [
            Column("Kind"),
            Column("Module"),
            Column("Session"),
            Column("Objective"),
            Column("Mapped to"),
        ],
        [],
        note="Module outcomes and session objectives that no programme outcome reaches through the "
        "upward links, or whose programme outcome is not visible to the person who made this "
        "report. These are the traceability gaps.",
    )
    for objective, module, event in chosen:
        if objective.level is ObjectiveLevel.PROGRAMME or objective.id in covered:
            continue
        loose.rows.append(
            [
                LEVEL_NAMES[objective.level.value],
                module.code if module else None,
                event.title if event else None,
                objective.text,
                items_of(objective.id),
            ]
        )
    about = [
        ("Report", "Traceability report"),
        (
            "Method",
            "Programme outcome, then the module outcomes and session objectives linked up to it, "
            "then the framework items they are accepted for.",
        ),
        (
            "Framework",
            f"{framework.name} ({framework.version_label})" if framework else "All frameworks",
        ),
        *common_about(ctx.visible, made.strftime("%Y-%m-%d %H:%M UTC"), not ctx.visible.view.full),
    ]
    return ReportDoc(
        key="traceability",
        title="Traceability report",
        about=about,
        method="Upward links from sessions to programme outcomes, then accepted mapping",
        made_on=made,
        sections=[traced, loose],
    )
