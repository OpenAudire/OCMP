"""Excel import of a framework (Slice 1.26, ADR 055): the workbook is turned into a framework pack
(ADR 036) and goes through the same checks, the same preview and the same import as a pack file.

The Framework sheet has one row (key, name, version, publisher, licence, profile, web address,
description) and the Items sheet one row per item (code, title, description, parent code). The items
keep the order of the rows. Problems found by the pack checks are reported with the sheet and row.
"""

from __future__ import annotations

import re
from typing import Any

from app.services.import_common import Plan, clean_rows, read_workbook
from app.services.import_fields import Lists
from app.services.import_fields_data import FRAMEWORK, FRAMEWORK_ITEMS, FRAMEWORK_SHEETS
from app.services.packs import FrameworkPack, PackProblem, check_pack


def workbook_to_pack(
    content: bytes, max_bytes: int
) -> tuple[dict[str, Any] | None, FrameworkPack | None, list[PackProblem]]:
    """The pack data made from a workbook, the checked pack, and every problem found.

    The first is ``None`` when the workbook cannot even be read as a pack."""
    plan = Plan(sheet_keys=tuple(s.key for s in FRAMEWORK_SHEETS))
    book = read_workbook(content, max_bytes, plan, FRAMEWORK_SHEETS)
    problems = [PackProblem(_where(p.sheet, p.row, p.column), p.message) for p in plan.problems]
    if problems and not book.rows:
        return None, None, problems
    heads = clean_rows(FRAMEWORK, book, Lists(), plan)
    items = clean_rows(FRAMEWORK_ITEMS, book, Lists(), plan)
    problems = [PackProblem(_where(p.sheet, p.row, p.column), p.message) for p in plan.problems]
    if len(heads) != 1:
        problems.append(
            PackProblem(
                FRAMEWORK.title,
                "The Framework sheet must have exactly one row (the framework itself).",
            )
        )
    if not items:
        problems.append(PackProblem(FRAMEWORK_ITEMS.title, "The Items sheet has no rows."))
    if problems:
        return None, None, problems

    head = heads[0][1]
    data: dict[str, Any] = {
        "format_version": 1,
        "metadata": {
            "key": head["key"],
            "name": head["name"],
            "version": head["version"],
            "publisher": head["publisher"],
            "licence": head.get("licence") or "",
            "profile": head.get("profile") or "core",
            "description": head.get("description") or "",
            "url": head.get("url"),
        },
        "items": [
            {
                "code": v["code"],
                "title": v["title"],
                "description": v.get("description") or "",
                "parent_code": v.get("parent_code"),
                "order": index,
            }
            for index, (_, v) in enumerate(items)
        ],
    }
    pack, found = check_pack(data)
    rows = [row.number for row, _ in items]
    return data, pack, [_translate(p, rows) for p in found]


def _where(sheet: str | None, row: int | None, column: str | None) -> str:
    parts = [sheet or "File"]
    if row is not None:
        parts.append(f"row {row}")
    if column:
        parts.append(column)
    return ", ".join(parts)


def _translate(problem: PackProblem, rows: list[int]) -> PackProblem:
    """A pack problem's path in the words of the workbook (the Items sheet and its row)."""
    found = re.match(r"^items\[(\d+)\](?:\.(\w+))?", problem.path)
    if found is not None and int(found.group(1)) < len(rows):
        column = {"parent_code": "Parent code", "code": "Code", "title": "Title"}.get(
            found.group(2) or "", found.group(2)
        )
        return PackProblem(
            _where(FRAMEWORK_ITEMS.title, rows[int(found.group(1))], column), problem.message
        )
    if problem.path.startswith("metadata"):
        return PackProblem(
            _where(FRAMEWORK.title, 2, problem.path.partition(".")[2] or None), problem.message
        )
    return problem
