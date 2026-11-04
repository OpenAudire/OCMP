"""What every Excel import shares (Slices 1.25 and 1.26, ADR 054): reading a workbook by its sheet
definitions, cleaning cells, collecting problems and the plan of what an import would do.

Nothing here touches the database.
"""

from __future__ import annotations

import io
import unicodedata
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

from openpyxl import load_workbook

from app.services.import_fields import (
    MAX_ROWS_PER_SHEET,
    Field,
    Kind,
    Lists,
    ParsedRow,
    Sheet,
)

MAX_PROBLEMS = 500


CREATE = "create"


UPDATE = "update"


UNCHANGED = "unchanged"


@dataclass(frozen=True)
class Problem:
    """Something wrong in the file. ``row`` is the row number in Excel (1 is the headings)."""

    sheet: str | None
    row: int | None
    column: str | None
    message: str


@dataclass
class RowPlan:
    sheet: str
    row: int
    external_id: str
    action: str
    label: str
    changes: list[str] = field(default_factory=list)


@dataclass
class Op:
    sheet: str
    row: int
    action: str
    external_id: str
    values: dict[str, Any]
    existing: Any | None = None


@dataclass
class Plan:
    problems: list[Problem] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    rows: list[RowPlan] = field(default_factory=list)
    ops: list[Op] = field(default_factory=list)
    truncated_problems: int = 0
    # The sheets of this kind of import (so the counts list every one, also the empty ones).
    sheet_keys: tuple[str, ...] = ()

    @property
    def valid(self) -> bool:
        """No problems and at least one row."""
        return not self.problems and bool(self.rows)

    @property
    def changes(self) -> bool:
        """Whether applying it would change anything."""
        return bool(self.ops)

    def counts(self) -> dict[str, dict[str, int]]:
        out: dict[str, dict[str, int]] = {
            key: {CREATE: 0, UPDATE: 0, UNCHANGED: 0} for key in self.sheet_keys
        }
        for row in self.rows:
            out.setdefault(row.sheet, {CREATE: 0, UPDATE: 0, UNCHANGED: 0})[row.action] += 1
        return out

    def add(self, sheet: str | None, row: int | None, column: str | None, message: str) -> None:
        if len(self.problems) >= MAX_PROBLEMS:
            self.truncated_problems += 1
            return
        self.problems.append(Problem(sheet, row, column, message))


def cell_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value == int(value):
        return str(int(value))
    return str(value).strip()


def clean_text(value: str, *, multiline: bool) -> str:
    kept = [
        c
        for c in value
        if unicodedata.category(c) != "Cc" or (multiline and c in "\n\t") or c == " "
    ]
    text = "".join(kept).strip()
    return text if multiline else " ".join(text.split())


@dataclass
class Book:
    rows: dict[str, list[ParsedRow]] = field(default_factory=dict)
    columns: dict[str, set[str]] = field(default_factory=dict)


def read_workbook(content: bytes, max_bytes: int, plan: Plan, sheets: tuple[Sheet, ...]) -> Book:
    """Read the given sheets by their titles. Problems go into ``plan``."""
    book = Book()
    if not content.strip():
        plan.add(None, None, None, "The file is empty.")
        return book
    if len(content) > max_bytes:
        plan.add(None, None, None, f"The file is larger than {max_bytes // (1024 * 1024)} MB.")
        return book
    try:
        workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    except Exception:  # openpyxl raises many kinds of errors for a file that is not a workbook
        plan.add(None, None, None, "This is not an Excel (.xlsx) workbook.")
        return book
    titles = {name.strip().casefold(): name for name in workbook.sheetnames}
    for sheet in sheets:
        name = titles.get(sheet.title.casefold())
        if name is None:
            continue
        rows = workbook[name].iter_rows(values_only=True)
        header = next(rows, None)
        if header is None or not any(cell_text(h) for h in header):
            continue
        by_header = {f.header.casefold(): f for f in sheet.fields}
        index: dict[int, Field] = {}
        for position, raw in enumerate(header):
            heading = cell_text(raw)
            if not heading:
                continue
            found = by_header.get(heading.casefold())
            if found is None:
                plan.warnings.append(f"{sheet.title}: the column '{heading}' is not used.")
            elif found.key in {f.key for f in index.values()}:
                plan.add(sheet.title, 1, heading, "This column heading appears twice.")
            else:
                index[position] = found
        parsed: list[ParsedRow] = []
        for number, row in enumerate(rows, start=2):
            if all(cell_text(c) == "" for c in row):
                continue
            if len(parsed) >= MAX_ROWS_PER_SHEET:
                plan.add(
                    sheet.title,
                    number,
                    None,
                    f"The sheet has more than {MAX_ROWS_PER_SHEET} rows; split the file.",
                )
                break
            parsed.append(
                ParsedRow(
                    number,
                    {f.key: row[p] if p < len(row) else None for p, f in index.items()},
                )
            )
        if parsed:
            present = {f.key for f in index.values()}
            for f in sheet.fields:
                if f.required and f.key not in present:
                    plan.add(sheet.title, 1, f.header, f"The column '{f.header}' is missing.")
            book.rows[sheet.key] = parsed
            book.columns[sheet.key] = present
    if not book.rows and not plan.problems:
        plan.add(None, None, None, "The workbook has no rows to import.")
    return book


def clean_value(f: Field, raw: Any, lists: Lists) -> tuple[Any, str | None]:
    """The cleaned value of a cell (``None`` when blank) and a problem, if any."""
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return None, (f"{f.header} is required." if f.required else None)
    if f.kind in (Kind.TEXT, Kind.LONG_TEXT, Kind.REFERENCE):
        value = clean_text(cell_text(raw), multiline=f.kind is Kind.LONG_TEXT)
        if not value:
            return None, (f"{f.header} is required." if f.required else None)
        if f.max_length is not None and len(value) > f.max_length:
            return None, f"{f.header} is longer than {f.max_length} characters."
        return value, None
    if f.kind is Kind.REFERENCES:
        parts = [p.strip() for p in cell_text(raw).split(";")]
        return list(dict.fromkeys(p for p in parts if p)) or None, None
    if f.kind is Kind.INTEGER:
        if isinstance(raw, bool):
            return None, f"{f.header} must be a whole number."
        try:
            number = Decimal(str(raw).strip())
        except InvalidOperation:
            return None, f"{f.header} must be a whole number."
        if number != number.to_integral_value():
            return None, f"{f.header} must be a whole number."
        whole = int(number)
        if (f.minimum is not None and whole < f.minimum) or (
            f.maximum is not None and whole > f.maximum
        ):
            return None, f"{f.header} must be from {int(f.minimum or 0)} to {int(f.maximum or 0)}."
        return whole, None
    if f.kind is Kind.DECIMAL:
        if isinstance(raw, bool):
            return None, f"{f.header} must be a number."
        try:
            dec = Decimal(str(raw).strip())
        except InvalidOperation:
            return None, f"{f.header} must be a number."
        if not dec.is_finite() or dec != dec.quantize(Decimal("0.1")):
            return None, f"{f.header} may have at most one decimal."
        if (f.minimum is not None and dec < Decimal(str(f.minimum))) or (
            f.maximum is not None and dec > Decimal(str(f.maximum))
        ):
            return None, f"{f.header} must be from {f.minimum:g} to {f.maximum:g}."
        return dec.quantize(Decimal("0.1")), None
    if f.kind is Kind.CHOICE:
        wanted = clean_text(cell_text(raw), multiline=False).casefold()
        allowed = {v.casefold(): v for v in lists.values(f.choices or "")}
        if wanted not in allowed:
            return (
                None,
                f"{f.header} '{cell_text(raw)[:60]}' is not in the list (see the Lists sheet).",
            )
        return allowed[wanted], None
    return None, f"{f.header} could not be read."


def clean_rows(
    sheet: Sheet, book: Book, lists: Lists, plan: Plan
) -> list[tuple[ParsedRow, dict[str, Any]]]:
    """Clean every row of a sheet; a row with a problem is dropped from the result (and the
    problems are in the plan, so the import cannot be applied)."""
    out: list[tuple[ParsedRow, dict[str, Any]]] = []
    seen: dict[str, int] = {}
    for row in book.rows.get(sheet.key, []):
        values: dict[str, Any] = {}
        bad = False
        for f in sheet.fields:
            if f.key not in book.columns[sheet.key]:
                continue
            value, problem = clean_value(f, row.cells.get(f.key), lists)
            if problem:
                plan.add(sheet.title, row.number, f.header, problem)
                bad = True
            values[f.key] = value
        ext = values.get("external_id")
        if ext is not None:
            if ext in seen:
                plan.add(
                    sheet.title,
                    row.number,
                    "External ID",
                    f"The External ID '{ext}' is also on row {seen[ext]}.",
                )
                bad = True
            else:
                seen[ext] = row.number
        if not bad:
            out.append((row, values))
    return out


def differences(existing: Any, wanted: dict[str, Any], names: dict[str, str]) -> list[str]:
    """The headings of the fields whose wanted value differs from the item's."""
    changed = []
    for key, heading in names.items():
        if key not in wanted:
            continue
        current = getattr(existing, key)
        if current in ("", None) and wanted[key] in ("", None):
            continue  # blank in the sheet, empty in the database
        if current != wanted[key]:
            changed.append(heading)
    return changed
