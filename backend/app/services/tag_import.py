"""Excel import of tag lists and their tags (Slice 1.26, ADR 055).

Like the curriculum import (ADR 054): ``check`` reads, checks and plans without writing anything
(the preview is the dry run), ``apply`` carries the plan out in one transaction through the
ordinary tag services, so everything is audited. A list is matched by its key, a tag by its label
in the list. Nothing is ever deleted or deactivated; a list's kind never changes; only
institution-wide lists are imported (a faculty's own lists are managed on the screen).
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ImportJob, TagList, TagValue, User
from app.models.tagging import TaggableType, TagListKind
from app.services import tagging
from app.services.authorization import ConflictError
from app.services.import_common import (
    CREATE,
    UNCHANGED,
    UPDATE,
    Book,
    Op,
    Plan,
    RowPlan,
    clean_rows,
    differences,
    read_workbook,
)
from app.services.import_fields import Lists
from app.services.import_fields_data import TAG_ENTITY_WORDS, TAG_LISTS, TAG_SHEETS, TAG_VALUES

KEY_PATTERN = re.compile(r"^[a-z0-9_-]+$")


@dataclass
class Existing:
    lists: dict[str, TagList]
    values: dict[tuple[uuid.UUID, str], TagValue]
    next_position: dict[uuid.UUID, int]


async def load_existing(db: AsyncSession) -> Existing:
    lists = {
        t.key: t for t in await db.scalars(select(TagList).where(TagList.deleted_at.is_(None)))
    }
    values: dict[tuple[uuid.UUID, str], TagValue] = {}
    next_position: dict[uuid.UUID, int] = {}
    for value in await db.scalars(
        select(TagValue).where(
            TagValue.deleted_at.is_(None),
            TagValue.tag_list_id.in_([t.id for t in lists.values()] or [uuid.uuid4()]),
        )
    ):
        values[(value.tag_list_id, value.label)] = value
        next_position[value.tag_list_id] = max(
            next_position.get(value.tag_list_id, 0), value.position + 1
        )
    return Existing(lists, values, next_position)


def _entity_types(words: list[str] | None) -> tuple[list[str] | None, str | None]:
    """The model's item types for the words of a cell; blank means all four."""
    if not words:
        return [t.value for t in TaggableType], None
    found: list[str] = []
    for word in words:
        mapped = TAG_ENTITY_WORDS.get(word.casefold())
        if mapped is None:
            return None, f"'{word}' is not programme, module, session or objective."
        found.append(mapped)
    return list(dict.fromkeys(found)), None


async def check(db: AsyncSession, content: bytes, *, max_bytes: int) -> Plan:
    """Read, check and plan an import of tag lists and tags. Writes nothing."""
    plan = Plan(sheet_keys=tuple(s.key for s in TAG_SHEETS))
    existing = await load_existing(db)
    book = read_workbook(content, max_bytes, plan, TAG_SHEETS)
    if plan.problems and not book.rows:
        return plan
    lists = Lists()
    list_rows = _unique_rows(TAG_LISTS.key, book, lists, plan)
    value_rows = clean_rows(TAG_VALUES, book, lists, plan)
    _plan_lists(plan, list_rows, existing, book)
    sheet_keys = {values["key"] for _, values in list_rows}
    _plan_values(plan, value_rows, existing, book, sheet_keys)
    if not plan.problems and not plan.rows:
        plan.add(None, None, None, "The workbook has no rows to import.")
    return plan


def _unique_rows(
    key: str, book: Book, lists: Lists, plan: Plan
) -> list[tuple[Any, dict[str, Any]]]:
    """The cleaned rows of the Tag lists sheet, with a repeated List key reported."""
    rows = clean_rows(TAG_LISTS, book, lists, plan)
    seen: dict[str, int] = {}
    kept = []
    for row, values in rows:
        name = values["key"]
        if name in seen:
            plan.add(
                TAG_LISTS.title, row.number, "List key", f"'{name}' is also on row {seen[name]}."
            )
            continue
        seen[name] = row.number
        kept.append((row, values))
    return kept


def _plan_lists(
    plan: Plan, rows: list[tuple[Any, dict[str, Any]]], existing: Existing, book: Book
) -> None:
    present = book.columns.get(TAG_LISTS.key, set())
    for row, values in rows:
        key = values["key"]
        if not KEY_PATTERN.match(key):
            plan.add(
                TAG_LISTS.title,
                row.number,
                "List key",
                "A list key may only have lower-case letters, digits, hyphens and underscores.",
            )
            continue
        if "applies_to" in present:
            types, problem = _entity_types(values.get("applies_to"))
            if problem:
                plan.add(TAG_LISTS.title, row.number, "Applies to", problem)
                continue
            values["entity_types"] = types
        found = existing.lists.get(key)
        if found is None:
            plan.rows.append(RowPlan(TAG_LISTS.key, row.number, key, CREATE, values["name"]))
            plan.ops.append(Op(TAG_LISTS.key, row.number, CREATE, key, values))
            continue
        if found.faculty_id is not None:
            plan.add(
                TAG_LISTS.title,
                row.number,
                "List key",
                "This list belongs to a faculty: manage it on the Tag lists screen.",
            )
            continue
        if "kind" in present and values.get("kind") != found.kind.value:
            plan.add(
                TAG_LISTS.title,
                row.number,
                "Kind",
                f"The kind of an existing list cannot be changed (it is {found.kind.value}).",
            )
            continue
        changed = differences(found, values, {"name": "Name", "description": "Description"})
        if "entity_types" in values and sorted(values["entity_types"]) != sorted(
            found.entity_types
        ):
            changed.append("Applies to")
        plan.rows.append(
            RowPlan(
                TAG_LISTS.key,
                row.number,
                key,
                UPDATE if changed else UNCHANGED,
                values.get("name") or found.name,
                changed,
            )
        )
        if changed:
            plan.ops.append(Op(TAG_LISTS.key, row.number, UPDATE, key, values, found))


def _plan_values(
    plan: Plan,
    rows: list[tuple[Any, dict[str, Any]]],
    existing: Existing,
    book: Book,
    sheet_lists: set[str],
) -> None:
    present = book.columns.get(TAG_VALUES.key, set())
    seen: dict[tuple[str, str], int] = {}
    codes: dict[tuple[str, str], str] = {}
    for (list_id, _), value in existing.values.items():
        owner = next((k for k, t in existing.lists.items() if t.id == list_id), None)
        if owner and value.code:
            codes[(owner, value.code)] = value.label
    for row, values in rows:
        list_key, label = values["list_key"], values["label"]
        if list_key not in sheet_lists and list_key not in existing.lists:
            plan.add(
                TAG_VALUES.title,
                row.number,
                "List key",
                f"No list has the key '{list_key}'.",
            )
            continue
        if (list_key, label) in seen:
            plan.add(
                TAG_VALUES.title,
                row.number,
                "Label",
                f"'{label}' is also on row {seen[(list_key, label)]} for this list.",
            )
            continue
        seen[(list_key, label)] = row.number
        tag_list = existing.lists.get(list_key)
        found = existing.values.get((tag_list.id, label)) if tag_list else None
        code = values.get("code") if "code" in present else None
        if code:
            holder = codes.get((list_key, code))
            if holder is not None and holder != label:
                plan.add(
                    TAG_VALUES.title,
                    row.number,
                    "Code",
                    f"The code '{code}' is already used by '{holder}' in this list.",
                )
                continue
            codes[(list_key, code)] = label
        ident = f"{list_key}/{label}"
        if found is None:
            plan.rows.append(RowPlan(TAG_VALUES.key, row.number, ident, CREATE, label))
            plan.ops.append(Op(TAG_VALUES.key, row.number, CREATE, ident, values))
            continue
        changed = differences(found, values, {"code": "Code", "description": "Description"})
        plan.rows.append(
            RowPlan(
                TAG_VALUES.key,
                row.number,
                ident,
                UPDATE if changed else UNCHANGED,
                label,
                changed,
            )
        )
        if changed:
            plan.ops.append(Op(TAG_VALUES.key, row.number, UPDATE, ident, values, found))


async def apply(db: AsyncSession, plan: Plan, actor: User) -> uuid.UUID:
    """Carry out a plan without problems, in one transaction. Returns the import job's id.

    Raises:
        ConflictError: If the plan has problems, or a key or label was taken meanwhile.
    """
    if plan.problems:
        raise ConflictError("The file has problems; fix them and preview again.")
    existing = await load_existing(db)
    lists = dict(existing.lists)
    positions = dict(existing.next_position)
    try:
        for op in (o for o in plan.ops if o.sheet == TAG_LISTS.key):
            v = op.values
            if op.existing is None:
                lists[op.external_id] = await tagging.create_tag_list(
                    db,
                    key=op.external_id,
                    name=v["name"],
                    kind=TagListKind(v["kind"]),
                    description=v.get("description") or "",
                    entity_types=[
                        TaggableType(t) for t in v.get("entity_types") or list(TaggableType)
                    ],
                    created_by_id=actor.id,
                )
            else:
                await tagging.update_tag_list(
                    db,
                    op.existing,
                    name=v.get("name"),
                    description=v["description"] or "" if "description" in v else None,
                    entity_types=[TaggableType(t) for t in v["entity_types"]]
                    if "entity_types" in v
                    else None,
                )
        for op in (o for o in plan.ops if o.sheet == TAG_VALUES.key):
            v = op.values
            if op.existing is None:
                tag_list = lists[v["list_key"]]
                position = positions.get(tag_list.id, 0)
                positions[tag_list.id] = position + 1
                await tagging.add_tag_value(
                    db,
                    tag_list,
                    v["label"],
                    code=v.get("code"),
                    description=v.get("description") or "",
                    position=position,
                    created_by_id=actor.id,
                )
            else:
                if "code" in v:
                    op.existing.code = v["code"]
                if "description" in v:
                    op.existing.description = v["description"] or ""
        await db.flush()
    except IntegrityError as exc:
        raise ConflictError(
            "The tags changed while the import was being applied. Preview the file again."
        ) from exc
    job = ImportJob(kind="tags", status="applied", summary=plan.counts(), created_by_id=actor.id)
    db.add(job)
    await db.flush()
    return job.id
