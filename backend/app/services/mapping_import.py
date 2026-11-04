"""Excel import of mapping links (Slice 1.26, ADR 055).

Each row names an objective of a draft version (by its External ID) and a framework item (by the
framework's key, optionally its version, and the item's code). A new pair becomes a link with the
source ``import``. By default it is only **suggested**: a reviewer decides on it in the review
queue, and the import never records a decision nobody made. Someone who may review mappings can
choose ``decided`` for links that were already reviewed elsewhere (an earlier accreditation): they
are then accepted with the method ``imported`` (no reviewer is recorded). A pair that is already
linked (in any state, rejected included) is left exactly as it is. ``check`` writes nothing (it is
the dry run); ``apply`` runs in one transaction through ``mapping.create_link``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    CurriculumVersion,
    Framework,
    FrameworkItem,
    ImportJob,
    MappingLink,
    Objective,
    User,
)
from app.models.framework import FrameworkStatus
from app.models.mapping import DepthMatch, MappingSource, MappingStatus
from app.services import curriculum_edit, mapping
from app.services.authorization import ConflictError
from app.services.import_common import (
    CREATE,
    UNCHANGED,
    Op,
    Plan,
    RowPlan,
    clean_rows,
    read_workbook,
)
from app.services.import_fields import Lists
from app.services.import_fields_data import MAPPING_SHEETS, MAPPINGS


@dataclass
class Existing:
    objectives: dict[str, Objective]
    frameworks: dict[str, list[Framework]]
    items: dict[tuple[uuid.UUID, str], FrameworkItem]
    links: dict[tuple[uuid.UUID, uuid.UUID], MappingLink]


async def load_existing(
    db: AsyncSession, version: CurriculumVersion, framework_keys: set[str]
) -> Existing:
    objectives = {
        str(o.external_id or o.id): o
        for o in await db.scalars(
            select(Objective).where(
                Objective.version_id == version.id, Objective.deleted_at.is_(None)
            )
        )
    }
    frameworks: dict[str, list[Framework]] = {}
    for framework in await db.scalars(
        select(Framework).where(
            Framework.key.in_(framework_keys or {""}), Framework.deleted_at.is_(None)
        )
    ):
        frameworks.setdefault(framework.key, []).append(framework)
    items = {
        (item.framework_id, item.code): item
        for item in await db.scalars(
            select(FrameworkItem).where(
                FrameworkItem.framework_id.in_(
                    [f.id for found in frameworks.values() for f in found] or [uuid.uuid4()]
                )
            )
        )
    }
    links = {
        (link.objective_id, link.framework_item_id): link
        for link in await db.scalars(
            select(MappingLink).where(
                MappingLink.objective_id.in_([o.id for o in objectives.values()] or [uuid.uuid4()]),
                MappingLink.deleted_at.is_(None),
            )
        )
    }
    return Existing(objectives, frameworks, items, links)


def _framework(found: list[Framework], version_label: str | None) -> tuple[Framework | None, str]:
    """The framework a row means, or a problem."""
    if version_label:
        match = [f for f in found if f.version_label == version_label]
        if len(match) == 1:
            return match[0], ""
        return None, f"The framework has no version '{version_label}'."
    active = [f for f in found if f.status is FrameworkStatus.ACTIVE]
    if len(active) == 1:
        return active[0], ""
    if not active:
        return None, "The framework has no active version: give a Framework version."
    return None, "The framework has several active versions: give a Framework version."


async def check(
    db: AsyncSession, version: CurriculumVersion, content: bytes, *, max_bytes: int
) -> Plan:
    """Read, check and plan an import of mapping links into ``version``. Writes nothing.

    Raises:
        ConflictError: If the version is not a draft.
    """
    curriculum_edit.ensure_editable(version)
    plan = Plan(sheet_keys=tuple(s.key for s in MAPPING_SHEETS))
    book = read_workbook(content, max_bytes, plan, MAPPING_SHEETS)
    if plan.problems and not book.rows:
        return plan
    rows = clean_rows(MAPPINGS, book, Lists(), plan)
    existing = await load_existing(db, version, {v["framework"] for _, v in rows})
    seen: dict[tuple[str, str, str | None, str], int] = {}
    for row, values in rows:
        ext = values["objective"]
        objective = existing.objectives.get(ext)
        if objective is None:
            plan.add(
                MAPPINGS.title,
                row.number,
                "Objective (External ID)",
                f"No objective of this version has the External ID '{ext}'.",
            )
            continue
        framework, problem = _framework(
            existing.frameworks.get(values["framework"], []), values.get("framework_version")
        )
        if framework is None:
            found = values["framework"] in existing.frameworks
            plan.add(
                MAPPINGS.title,
                row.number,
                "Framework version" if found else "Framework key",
                problem if found else f"No framework has the key '{values['framework']}'.",
            )
            continue
        item = existing.items.get((framework.id, values["code"]))
        if item is None:
            plan.add(
                MAPPINGS.title,
                row.number,
                "Framework item code",
                f"The framework has no item with the code '{values['code']}'.",
            )
            continue
        pair = (ext, framework.key, framework.version_label, item.code)
        if pair in seen:
            plan.add(
                MAPPINGS.title,
                row.number,
                "Framework item code",
                f"This objective and item are also on row {seen[pair]}.",
            )
            continue
        seen[pair] = row.number
        values["_objective"] = objective
        values["_item"] = item
        label = f"{ext} → {framework.key} {item.code}"
        link = existing.links.get((objective.id, item.id))
        if link is not None:
            plan.rows.append(
                RowPlan(
                    MAPPINGS.key,
                    row.number,
                    ext,
                    UNCHANGED,
                    label,
                    [f"already linked ({link.status.value})"],
                )
            )
            continue
        plan.rows.append(RowPlan(MAPPINGS.key, row.number, ext, CREATE, label))
        plan.ops.append(Op(MAPPINGS.key, row.number, CREATE, ext, values))
    if not plan.problems and not plan.rows:
        plan.add(None, None, None, "The workbook has no rows to import.")
    return plan


async def apply(
    db: AsyncSession, version: CurriculumVersion, plan: Plan, actor: User, *, decided: bool = False
) -> uuid.UUID:
    """Make the suggested links of a plan without problems, in one transaction.

    Raises:
        ConflictError: If the plan has problems, or a pair was linked meanwhile.
    """
    if plan.problems:
        raise ConflictError("The file has problems; fix them and preview again.")
    curriculum_edit.ensure_editable(version)
    try:
        for op in plan.ops:
            v: dict[str, Any] = op.values
            link = await mapping.create_link(
                db,
                v["_objective"],
                v["_item"],
                source=MappingSource.IMPORT,
                creator=actor,
                coverage=v["coverage"],
                depth_match=DepthMatch(v["depth"]) if v.get("depth") else DepthMatch.MATCHES,
                rationale=v.get("rationale") or "",
            )
            if not decided:
                link.status = MappingStatus.SUGGESTED
                link.accept_method = None
    except IntegrityError as exc:
        raise ConflictError(
            "The mappings changed while the import was being applied. Preview the file again."
        ) from exc
    job = ImportJob(
        kind="mappings",
        version_id=version.id,
        status="applied",
        summary={**plan.counts(), "decided": {"links": len(plan.ops) if decided else 0}},
        created_by_id=actor.id,
    )
    db.add(job)
    await db.flush()
    return job.id
