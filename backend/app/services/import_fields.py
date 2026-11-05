"""The fields of the curriculum import and the Excel template made from them (Slice 1.25, ADR 054).

One list of field definitions (``SHEETS``) drives **both** the template (headings, dropdowns, the
whole-number and decimal checks, the instructions) **and** the reading and checking of an uploaded
workbook, so the two cannot drift apart (a test compares them). Slice 1.27's full export writes
the same sheets through ``build_workbook``.

Nothing here touches the database: the dropdown lists are passed in.
"""

from __future__ import annotations

import io
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from app.models.curriculum import ObjectiveDomain, PhaseKind
from app.models.framework import FrameworkProfile
from app.models.mapping import DepthMatch
from app.models.tagging import TagListKind

MAX_ROWS_PER_SHEET = 5000
TEMPLATE_VALIDATED_ROWS = 1000
LIST_SHEET = "Lists"
INSTRUCTIONS_SHEET = "Instructions"


class Kind(StrEnum):
    TEXT = "text"
    LONG_TEXT = "long_text"
    INTEGER = "integer"
    DECIMAL = "decimal"
    CHOICE = "choice"
    REFERENCE = "reference"  # an external id on another sheet (or already in the version)
    REFERENCES = "references"  # several external ids separated by semicolons


@dataclass(frozen=True)
class Field:
    key: str
    header: str
    kind: Kind
    help: str
    required: bool = False
    max_length: int | None = None
    minimum: float | None = None
    maximum: float | None = None
    # For CHOICE: the name of the list in ``Lists`` (see ``LIST_NAMES``).
    choices: str | None = None
    width: int = 22


@dataclass(frozen=True)
class Sheet:
    key: str
    title: str
    about: str
    fields: tuple[Field, ...]

    def field(self, key: str) -> Field:
        return next(f for f in self.fields if f.key == key)


EXTERNAL_ID = Field(
    "external_id",
    "External ID",
    Kind.TEXT,
    "Your own identifier for this row (for example the code in your student system). It must be "
    "unique in the sheet. Importing the same External ID again updates the item instead of "
    "making a second one.",
    required=True,
    max_length=128,
)

TAGS = Field(
    "tags",
    "Tags",
    Kind.REFERENCES,
    "Tags to put on this item, separated by semicolons, each written as the key of a tag list, a "
    "colon and the tag's label: for example 'theme: Ethics; keyword: Consent'. The list and the "
    "tag must already exist (see the Tag lists and Tag values sheets of the tags import) and the "
    "list must apply to this kind of item. They are set directly on this item and are not passed "
    "on to others. Tags are added, never removed; blank changes nothing.",
    width=36,
)

PHASES = Sheet(
    "phases",
    "Phases",
    "Years, phases, blocks or longitudinal threads of the curriculum version.",
    (
        EXTERNAL_ID,
        Field("name", "Name", Kind.TEXT, "For example Year 1.", required=True, max_length=255),
        Field(
            "kind",
            "Kind",
            Kind.CHOICE,
            "year, phase, block or longitudinal_thread. Blank means year.",
            choices="phase_kind",
        ),
    ),
)

MODULES = Sheet(
    "modules",
    "Modules",
    "Modules (courses) of the version.",
    (
        EXTERNAL_ID,
        Field(
            "code",
            "Code",
            Kind.TEXT,
            "The module code. It must be unique in the version.",
            required=True,
            max_length=32,
            width=14,
        ),
        Field("name", "Name", Kind.TEXT, "The module name.", required=True, max_length=255),
        Field(
            "phase",
            "Phase (External ID)",
            Kind.REFERENCE,
            "The External ID of the module's phase (on the Phases sheet or already in the "
            "version). Blank means a longitudinal module with no phase.",
            width=24,
        ),
        Field(
            "credits",
            "Credits",
            Kind.DECIMAL,
            "Credits, with at most one decimal.",
            minimum=0,
            maximum=9999.9,
            width=10,
        ),
        Field(
            "nqf_level",
            "NQF level",
            Kind.INTEGER,
            "A whole number from 1 to 10.",
            minimum=1,
            maximum=10,
            width=10,
        ),
        Field("description", "Description", Kind.LONG_TEXT, "Optional.", width=40),
        Field(
            "external_lms_ref",
            "LMS reference",
            Kind.TEXT,
            "Optional reference to the module in your learning management system.",
            max_length=255,
        ),
        TAGS,
    ),
)

SESSIONS = Sheet(
    "sessions",
    "Sessions",
    "Learning events: lectures, tutorials, practicals, placements.",
    (
        EXTERNAL_ID,
        Field(
            "module",
            "Module (External ID)",
            Kind.REFERENCE,
            "The External ID of the session's module (on the Modules sheet or already in the "
            "version).",
            required=True,
            width=24,
        ),
        Field("title", "Title", Kind.TEXT, "The session title.", required=True, max_length=255),
        Field(
            "format",
            "Teaching format",
            Kind.CHOICE,
            "A value of a teaching-method tag list (see the Lists sheet).",
            choices="format",
        ),
        Field(
            "contact_minutes",
            "Contact minutes",
            Kind.INTEGER,
            "Whole minutes of contact time. Blank means 0.",
            minimum=0,
            maximum=100000,
            width=12,
        ),
        Field(
            "self_study_minutes",
            "Self-study minutes",
            Kind.INTEGER,
            "Whole minutes of self-study. Blank means 0.",
            minimum=0,
            maximum=100000,
            width=12,
        ),
        Field(
            "week",
            "Week",
            Kind.INTEGER,
            "The week of the session (0 or more), if it has one.",
            minimum=0,
            maximum=200,
            width=8,
        ),
        Field("description", "Description", Kind.LONG_TEXT, "Optional.", width=40),
        Field(
            "external_lms_ref",
            "LMS reference",
            Kind.TEXT,
            "Optional reference to the session in your learning management system.",
            max_length=255,
        ),
        TAGS,
    ),
)

OBJECTIVES = Sheet(
    "objectives",
    "Objectives",
    "Programme outcomes, module outcomes and session objectives.",
    (
        EXTERNAL_ID,
        Field(
            "level",
            "Level",
            Kind.CHOICE,
            "programme, module or session.",
            required=True,
            choices="objective_level",
            width=12,
        ),
        Field(
            "owner",
            "Owner (External ID)",
            Kind.REFERENCE,
            "For a module outcome the module's External ID, for a session objective the "
            "session's External ID. Leave blank for a programme outcome.",
            width=24,
        ),
        Field(
            "text", "Text", Kind.LONG_TEXT, "The wording of the objective.", required=True, width=70
        ),
        Field(
            "domain",
            "Domain",
            Kind.CHOICE,
            "knowledge, skill or attitude (optional).",
            choices="domain",
            width=12,
        ),
        Field(
            "taxonomy_level",
            "Taxonomy level",
            Kind.CHOICE,
            "A level of your taxonomy scale (see the Lists sheet; optional).",
            choices="taxonomy_level",
        ),
        Field(
            "broader",
            "Broader objectives (External IDs)",
            Kind.REFERENCES,
            "External IDs of the broader objectives this one contributes to, separated by "
            "semicolons: for a module outcome programme outcomes; for a session objective "
            "programme outcomes or outcomes of its own module. Links are added, never removed; "
            "blank changes nothing.",
            width=30,
        ),
        TAGS,
    ),
)

SHEETS: tuple[Sheet, ...] = (PHASES, MODULES, SESSIONS, OBJECTIVES)
SHEET_BY_KEY = {s.key: s for s in SHEETS}

# Objective level words in the sheet and the model's levels.
LEVEL_WORDS = {"programme": "programme", "module": "module", "session": "learning_event"}

# The fixed lists; the others come from the database (``Lists.dynamic``).
LIST_NAMES = {
    "phase_kind": "Phase kind",
    "objective_level": "Objective level",
    "domain": "Domain",
    "format": "Teaching format",
    "taxonomy_level": "Taxonomy level",
    "tag_kind": "Kind of tag list",
    "depth": "Depth",
    "framework_profile": "Framework profile",
}
FIXED_LISTS: dict[str, tuple[str, ...]] = {
    "phase_kind": tuple(k.value for k in PhaseKind),
    "objective_level": tuple(LEVEL_WORDS),
    "domain": tuple(d.value for d in ObjectiveDomain),
    "tag_kind": tuple(k.value for k in TagListKind),
    "depth": tuple(d.value for d in DepthMatch),
    "framework_profile": tuple(p.value for p in FrameworkProfile),
}


@dataclass(frozen=True)
class Lists:
    """The dropdown values: the fixed ones plus the institution's teaching formats and taxonomy
    levels."""

    formats: tuple[str, ...] = ()
    taxonomy_levels: tuple[str, ...] = ()

    def values(self, name: str) -> tuple[str, ...]:
        if name == "format":
            return self.formats
        if name == "taxonomy_level":
            return self.taxonomy_levels
        return FIXED_LISTS[name]


CURRICULUM_HOW = (
    "  Fill in the sheets you need; leave the others empty.",
    "  Upload the file on the Import page, choose the version and read the preview.",
    "  Nothing is changed until you confirm. Only draft versions can be imported into.",
    "  Every row needs an External ID of your own. Importing the same External ID again updates "
    "that item; a new External ID makes a new item. An import never deletes anything.",
    "  A column you remove from a sheet is left alone. A column you keep and leave blank clears "
    "that value (except Broader objectives and Tags, which only add).",
    "  Do not put the names of people or patients in any cell.",
)


def instructions(
    sheets: tuple[Sheet, ...] = SHEETS,
    heading: str = "Curriculum structure and objectives: Excel template",
    how: Sequence[str] = CURRICULUM_HOW,
) -> list[str]:
    """The text of the Instructions sheet, made from the definitions."""
    lines = [heading, "", "How this works", *how, ""]
    for sheet in sheets:
        lines.append(f"{sheet.title}: {sheet.about}")
        for f in sheet.fields:
            required = "required" if f.required else "optional"
            lines.append(f"  {f.header} ({required}): {f.help}")
        lines.append("")
    return lines


def _text_cell(cell: Any, value: Any) -> None:
    cell.value = value
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@"):
        cell.data_type = "s"


def build_workbook(
    lists: Lists,
    rows: Mapping[str, Sequence[Sequence[Any]]] | None = None,
    sheets: tuple[Sheet, ...] = SHEETS,
    heading: str = "Curriculum structure and objectives: Excel template",
    how: Sequence[str] = CURRICULUM_HOW,
) -> bytes:
    """The template: one sheet for each of ``sheets`` with its headings, dropdowns and checks, an
    Instructions sheet and a Lists sheet. With ``rows`` (sheet key to rows of cell values in the
    order of the fields) the sheets are filled: the full export of Slice 1.27 uses that."""
    book = Workbook()
    first = book.active
    assert first is not None
    book.remove(first)

    guide = book.create_sheet(INSTRUCTIONS_SHEET)
    for line in instructions(sheets, heading, how):
        guide.append([line])
    guide["A1"].font = Font(bold=True, size=14)
    guide.column_dimensions["A"].width = 130
    for cell in guide["A"]:
        cell.alignment = Alignment(wrap_text=True, vertical="top")

    listing = book.create_sheet(LIST_SHEET)
    list_columns: dict[str, str] = {}
    used = {f.choices for sheet in sheets for f in sheet.fields if f.choices}
    for index, name in enumerate((n for n in LIST_NAMES if n in used), start=1):
        values = lists.values(name)
        letter = get_column_letter(index)
        listing.cell(row=1, column=index, value=LIST_NAMES[name]).font = Font(bold=True)
        for offset, value in enumerate(values, start=2):
            _text_cell(listing.cell(row=offset, column=index), value)
        listing.column_dimensions[letter].width = 34
        if values:
            list_columns[name] = f"{LIST_SHEET}!${letter}$2:${letter}${len(values) + 1}"

    required_fill = PatternFill("solid", start_color="1F6F6B")
    optional_fill = PatternFill("solid", start_color="5B8F8B")
    for sheet in sheets:
        ws = book.create_sheet(sheet.title)
        ws.append([f.header for f in sheet.fields])
        for column, f in enumerate(sheet.fields, start=1):
            head = ws.cell(row=1, column=column)
            head.font = Font(bold=True, color="FFFFFF")
            head.fill = required_fill if f.required else optional_fill
            head.alignment = Alignment(vertical="center", wrap_text=True)
            head.comment = Comment(("Required. " if f.required else "Optional. ") + f.help, "OCMP")
            ws.column_dimensions[get_column_letter(column)].width = f.width
        ws.freeze_panes = "A2"
        for cells in (rows or {}).get(sheet.key, ()):
            ws.append([None] * len(sheet.fields))
            for column, value in enumerate(cells, start=1):
                _text_cell(ws.cell(row=ws.max_row, column=column), value)
        last = max(TEMPLATE_VALIDATED_ROWS, ws.max_row)
        for column, f in enumerate(sheet.fields, start=1):
            letter = get_column_letter(column)
            span = f"{letter}2:{letter}{last}"
            validation: DataValidation | None = None
            if f.kind is Kind.INTEGER:
                validation = DataValidation(
                    type="whole",
                    operator="between",
                    formula1=str(int(f.minimum or 0)),
                    formula2=str(int(f.maximum or 100000)),
                    allow_blank=True,
                    showErrorMessage=True,
                    errorTitle=f.header,
                    error=f"Enter a whole number from {int(f.minimum or 0)} to "
                    f"{int(f.maximum or 100000)}.",
                )
            elif f.kind is Kind.DECIMAL:
                validation = DataValidation(
                    type="decimal",
                    operator="between",
                    formula1=str(f.minimum or 0),
                    formula2=str(f.maximum or 100000),
                    allow_blank=True,
                    showErrorMessage=True,
                    errorTitle=f.header,
                    error=f"Enter a number from {f.minimum or 0:g} to {f.maximum or 100000:g}.",
                )
            elif f.kind is Kind.CHOICE and f.choices in list_columns:
                validation = DataValidation(
                    type="list",
                    formula1=f"={list_columns[f.choices]}",
                    allow_blank=True,
                    showErrorMessage=True,
                    errorTitle=f.header,
                    error="Choose a value from the list (see the Lists sheet).",
                )
            if validation is not None:
                ws.add_data_validation(validation)
                validation.add(span)

    out = io.BytesIO()
    book.save(out)
    return out.getvalue()


@dataclass
class ParsedRow:
    """One row of a sheet as read: its number in the file and the raw cells by field key."""

    number: int
    cells: dict[str, Any] = field(default_factory=dict)
