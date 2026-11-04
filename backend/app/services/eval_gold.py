"""Gold sets for the evaluation harness: the Excel template, reading it, saving it (Slice 1.19).

A gold set is filled in by hand in Excel (or written as JSON for the demo): one row per
objective and framework item, with the coverage (0 to 5) and the depth a person decided. An
objective that maps to nothing has a row with the objective text and no code. Every problem
found is reported with its row number; nothing is saved unless the whole file is sound.
"""

from __future__ import annotations

import io
import re
import uuid
from dataclasses import dataclass, field
from typing import Any

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Framework, FrameworkItem, GoldCase, GoldLink, GoldSet
from app.models.mapping import DepthMatch
from app.services.audit import audit_operation
from app.services.authorization import ConflictError, InvalidRequestError

MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_ROWS = 5000
MAX_PROBLEMS = 50
OBJECTIVE_MAX = 2000
SHEET = "Gold set"
HEADERS = ("Objective text", "Framework item code", "Coverage (0-5)", "Depth", "Notes")
DEPTHS = tuple(d.value for d in DepthMatch)
_DEPTH_ALIASES = {d.replace("_", " "): d for d in DEPTHS}

INSTRUCTIONS = (
    "How to fill in this gold set",
    "",
    "A gold set is the answer key the AI is marked against. It must be decided by people, "
    "without looking at what the AI suggested.",
    "",
    "One row for each objective and framework item it maps to:",
    "  Objective text - copy the objective's wording exactly as it is in the curriculum. The "
    "same wording on several rows is one objective.",
    "  Framework item code - the code in the framework (the 'Framework items' sheet lists them).",
    "  Coverage (0-5) - how much of the item the objective covers: 0 = no, 1 = a mention, "
    "5 = fully. Use 0 to record 'I looked and it does not map here'.",
    "  Depth - below, matches, above, or not_applicable (the item has no verb or level). "
    "Leave blank if you are not sure.",
    "  Notes - anything you want to remember; never read by the program.",
    "",
    "An objective that maps to nothing in the framework: one row with the objective text and "
    "the code, coverage and depth left blank.",
    "",
    "Do not put the names of people or patients in any cell.",
    "Delete nothing from the header row and do not rename the sheets.",
)


@dataclass(frozen=True)
class RowIn:
    code: str
    coverage: int
    depth: DepthMatch | None
    row: int


@dataclass
class CaseIn:
    text: str
    rows: list[RowIn] = field(default_factory=list)


@dataclass(frozen=True)
class Problem:
    row: int | None
    message: str


@dataclass
class ParsedGold:
    cases: list[CaseIn] = field(default_factory=list)
    problems: list[Problem] = field(default_factory=list)

    @property
    def links(self) -> int:
        return sum(len(c.rows) for c in self.cases)

    @property
    def empty_cases(self) -> int:
        return sum(1 for c in self.cases if not c.rows)


class GoldSetInvalid(InvalidRequestError):
    """The file has problems; ``problems`` lists them (row number and a plain sentence)."""

    def __init__(self, problems: list[Problem]) -> None:
        super().__init__("The gold set has problems; nothing was saved.")
        self.problems = problems


def normal(text: str) -> str:
    """Objective wording as compared: spaces collapsed, case ignored."""
    return re.sub(r"\s+", " ", text).strip().casefold()


# --- Writing the template and exports ------------------------------------------------------


def _write_sheets(
    items: list[tuple[str, str]], rows: list[tuple[Any, ...]], *, framework_name: str | None
) -> bytes:
    book = Workbook()
    sheet = book.active
    assert sheet is not None
    sheet.title = SHEET
    sheet.append(list(HEADERS))
    for row in rows:
        sheet.append(list(row))
    head = PatternFill("solid", start_color="1F6F6B")
    for cell in sheet[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = head
        cell.alignment = Alignment(vertical="center", wrap_text=True)
    for column, width in zip("ABCDE", (70, 22, 16, 16, 40), strict=True):
        sheet.column_dimensions[column].width = width
    sheet.freeze_panes = "A2"

    last = max(MAX_ROWS, len(rows) + 2)
    coverage = DataValidation(
        type="whole",
        operator="between",
        formula1="0",
        formula2="5",
        allow_blank=True,
        showErrorMessage=True,
        errorTitle="Coverage",
        error="Enter a whole number from 0 to 5.",
    )
    depth = DataValidation(
        type="list",
        formula1='"' + ",".join(DEPTHS) + '"',
        allow_blank=True,
        showErrorMessage=True,
        errorTitle="Depth",
        error="Choose below, matches, above or not_applicable.",
    )
    sheet.add_data_validation(coverage)
    sheet.add_data_validation(depth)
    coverage.add(f"C2:C{last}")
    depth.add(f"D2:D{last}")

    guide = book.create_sheet("Instructions")
    for line in INSTRUCTIONS:
        guide.append([line])
    guide["A1"].font = Font(bold=True, size=14)
    guide.column_dimensions["A"].width = 120
    for cell in guide["A"]:
        cell.alignment = Alignment(wrap_text=True, vertical="top")

    if items:
        listing = book.create_sheet("Framework items")
        listing.append(["Code", f"Title ({framework_name})" if framework_name else "Title"])
        for code, title in items:
            listing.append([code, title])
        listing["A1"].font = Font(bold=True)
        listing["B1"].font = Font(bold=True)
        listing.column_dimensions["A"].width = 18
        listing.column_dimensions["B"].width = 90
        codes = DataValidation(
            type="list",
            formula1=f"'Framework items'!$A$2:$A${len(items) + 1}",
            allow_blank=True,
            showErrorMessage=True,
            errorTitle="Framework item code",
            error="Choose a code from the 'Framework items' sheet.",
        )
        sheet.add_data_validation(codes)
        codes.add(f"B2:B{last}")
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()


async def _items_of(db: AsyncSession, framework_id: uuid.UUID) -> list[tuple[str, str]]:
    rows = await db.execute(
        select(FrameworkItem.code, FrameworkItem.title)
        .where(FrameworkItem.framework_id == framework_id)
        .order_by(FrameworkItem.code)
    )
    return [(code, title) for code, title in rows]


async def build_template(db: AsyncSession, framework: Framework | None) -> bytes:
    """The empty workbook; with a framework it lists the item codes and offers them in a list."""
    items = await _items_of(db, framework.id) if framework else []
    return _write_sheets(items, [], framework_name=framework.name if framework else None)


async def export_gold_set(db: AsyncSession, gold_set: GoldSet) -> bytes:
    """The gold set in the same layout as the template (it can be edited and imported again)."""
    framework = await db.get(Framework, gold_set.framework_id)
    items = await _items_of(db, gold_set.framework_id)
    cases = list(
        await db.scalars(
            select(GoldCase).where(GoldCase.gold_set_id == gold_set.id).order_by(GoldCase.position)
        )
    )
    rows: list[tuple[Any, ...]] = []
    for case in cases:
        links = list(
            await db.scalars(
                select(GoldLink).where(GoldLink.case_id == case.id).order_by(GoldLink.item_code)
            )
        )
        if not links:
            rows.append((case.objective_text, None, None, None, None))
        for link in links:
            rows.append(
                (
                    case.objective_text,
                    link.item_code,
                    link.coverage,
                    link.depth.value if link.depth else None,
                    None,
                )
            )
    return _write_sheets(items, rows, framework_name=framework.name if framework else None)


# --- Reading -------------------------------------------------------------------------------


def _cell_text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _coverage(value: Any) -> int | None:
    """A whole number from 0 to 5, or None."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        number = float(value)
    else:
        try:
            number = float(str(value).strip())
        except ValueError:
            return None
    if number != int(number) or not 0 <= number <= 5:
        return None
    return int(number)


def read_workbook(content: bytes) -> ParsedGold:
    """Read the template's first sheet. Problems are collected, not raised."""
    parsed = ParsedGold()
    if len(content) > MAX_FILE_BYTES:
        parsed.problems.append(Problem(None, "The file is larger than 5 MB."))
        return parsed
    try:
        book = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    except Exception:  # openpyxl raises many kinds of errors for a file that is not a workbook
        parsed.problems.append(Problem(None, "This is not an Excel (.xlsx) workbook."))
        return parsed
    sheet = book[SHEET] if SHEET in book.sheetnames else book[book.sheetnames[0]]
    rows = sheet.iter_rows(values_only=True)
    header = next(rows, None)
    if header is None or not any(header):
        parsed.problems.append(Problem(1, "The first row must hold the column headings."))
        return parsed
    names = [_cell_text(h).casefold() for h in header]

    def column(*starts: str) -> int | None:
        for index, name in enumerate(names):
            if any(name.startswith(s) for s in starts):
                return index
        return None

    c_text, c_code = column("objective"), column("framework item", "code")
    c_cov, c_depth = column("coverage"), column("depth")
    if c_text is None or c_code is None or c_cov is None or c_depth is None:
        parsed.problems.append(
            Problem(
                1,
                "The headings must be: Objective text, Framework item code, Coverage (0-5), Depth.",
            )
        )
        return parsed

    by_text: dict[str, CaseIn] = {}
    seen: set[tuple[str, str]] = set()
    count = 0
    for number, row in enumerate(rows, start=2):
        cells = list(row) + [None] * 8
        text = " ".join(_cell_text(cells[c_text]).split())
        code = _cell_text(cells[c_code])
        raw_cov, raw_depth = cells[c_cov], _cell_text(cells[c_depth])
        if not text and not code and _cell_text(raw_cov) == "" and not raw_depth:
            continue
        count += 1
        if count > MAX_ROWS:
            parsed.problems.append(Problem(number, f"More than {MAX_ROWS} rows."))
            break
        if not text:
            parsed.problems.append(Problem(number, "The objective text is empty."))
            continue
        if len(text) > OBJECTIVE_MAX:
            parsed.problems.append(Problem(number, "The objective text is too long."))
            continue
        case = by_text.get(normal(text))
        if case is None:
            case = by_text[normal(text)] = CaseIn(text)
            parsed.cases.append(case)
        if not code:
            if _cell_text(raw_cov) or raw_depth:
                parsed.problems.append(
                    Problem(number, "A coverage or depth needs a framework item code.")
                )
            continue
        cov = _coverage(raw_cov) if _cell_text(raw_cov) else None
        if cov is None:
            parsed.problems.append(Problem(number, "The coverage must be a whole number 0 to 5."))
            continue
        depth: DepthMatch | None = None
        if raw_depth:
            key = raw_depth.casefold()
            found = key if key in DEPTHS else _DEPTH_ALIASES.get(key)
            if found is None:
                parsed.problems.append(
                    Problem(number, "The depth must be below, matches, above or not_applicable.")
                )
                continue
            depth = DepthMatch(found)
        if (normal(text), code.casefold()) in seen:
            parsed.problems.append(
                Problem(number, "This objective already has a row for this item code.")
            )
            continue
        seen.add((normal(text), code.casefold()))
        case.rows.append(RowIn(code, cov, depth, number))
    if not parsed.cases and not parsed.problems:
        parsed.problems.append(Problem(None, "The sheet has no objectives."))
    return parsed


def read_json(data: dict[str, Any]) -> ParsedGold:
    """The demo gold set, written as JSON: ``{"cases": [{"objective", "links": [...]}]}``."""
    parsed = ParsedGold()
    for index, raw in enumerate(data.get("cases", []), start=1):
        case = CaseIn(" ".join(str(raw.get("objective", "")).split()))
        if not case.text:
            parsed.problems.append(Problem(index, "The objective text is empty."))
            continue
        for link in raw.get("links", []):
            depth = DepthMatch(link["depth"]) if link.get("depth") else None
            case.rows.append(RowIn(str(link["code"]), int(link["coverage"]), depth, index))
        parsed.cases.append(case)
    return parsed


# --- Checking against the framework and saving ----------------------------------------------


async def check_codes(db: AsyncSession, framework_id: uuid.UUID, parsed: ParsedGold) -> None:
    """Add a problem for every item code the framework does not have."""
    known = {code.casefold(): code for code, _ in await _items_of(db, framework_id)}
    for case in parsed.cases:
        fixed: list[RowIn] = []
        for row in case.rows:
            code = known.get(row.code.casefold())
            if code is None:
                parsed.problems.append(
                    Problem(row.row, f"The framework has no item with the code {row.code[:40]}.")
                )
                continue
            fixed.append(RowIn(code, row.coverage, row.depth, row.row))
        case.rows = fixed


async def preview(db: AsyncSession, framework: Framework, content: bytes) -> ParsedGold:
    parsed = read_workbook(content)
    await check_codes(db, framework.id, parsed)
    parsed.problems.sort(key=lambda p: p.row or 0)
    parsed.problems = parsed.problems[:MAX_PROBLEMS]
    return parsed


async def save_gold_set(
    db: AsyncSession,
    *,
    actor_id: uuid.UUID | None,
    name: str,
    description: str,
    framework: Framework,
    parsed: ParsedGold,
    is_demo: bool = False,
) -> GoldSet:
    """Save a checked gold set.

    Raises:
        GoldSetInvalid: If the parsed set has problems.
        InvalidRequestError: For an empty name or no objectives.
        ConflictError: If a gold set of that name exists.
    """
    name = " ".join(name.split())
    if not name or len(name) > 200:
        raise InvalidRequestError("Give the gold set a name of up to 200 characters.")
    if parsed.problems:
        raise GoldSetInvalid(parsed.problems[:MAX_PROBLEMS])
    if not parsed.cases:
        raise InvalidRequestError("The gold set has no objectives.")
    if await db.scalar(
        select(GoldSet.id).where(GoldSet.name == name, GoldSet.deleted_at.is_(None))
    ):
        raise ConflictError("A gold set with this name already exists.")
    with audit_operation("eval.gold_set_import", actor_id=actor_id):
        gold = GoldSet(
            name=name,
            description=description.strip()[:2000],
            framework_id=framework.id,
            is_demo=is_demo,
            created_by_id=actor_id,
        )
        db.add(gold)
        await db.flush()
        for position, case in enumerate(parsed.cases, start=1):
            row = GoldCase(
                gold_set_id=gold.id,
                position=position,
                objective_text=case.text,
                created_by_id=actor_id,
            )
            db.add(row)
            await db.flush()
            for link in case.rows:
                db.add(
                    GoldLink(
                        case_id=row.id,
                        item_code=link.code,
                        coverage=link.coverage,
                        depth=link.depth,
                        created_by_id=actor_id,
                    )
                )
        await db.flush()
    return gold
