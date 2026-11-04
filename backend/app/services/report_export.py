"""Report documents and their export to Excel and PDF (Slice 1.22, ADR 051).

A report is built once as a ``ReportDoc`` (a title, lines saying how it was made, and tables) and
then shown on screen, written to a workbook or written to a PDF. **Every sheet and every page
states the report's method and the time it was made** (brief: "every report states its method and
date"): the workbook repeats them at the top of each sheet and the PDF in the footer of each page.

Text in a report comes from people (objective wording, module names), so it is never trusted:

* in a workbook a cell that starts like a formula (``=``, ``+``, ``-``, ``@``) is written as text
  (a spreadsheet would otherwise run it);
* in a PDF text is escaped, wrapped, and limited to the characters the built-in PDF font can
  draw (Western European letters and common punctuation; anything else becomes ``?``). Other
  scripts need an embedded font, which this slice does not add.

File names are fixed and never contain user text.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any
from xml.sax.saxutils import escape

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

Cell = str | int | float | None

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
PDF = "application/pdf"
MAX_ROWS = 20_000
SHEET_NAME_MAX = 31
_BAD_SHEET = re.compile(r"[\[\]:*?/\\]")
_FORMULA_START = ("=", "+", "-", "@", "\t", "\r")


class Kind(StrEnum):
    TEXT = "text"
    INTEGER = "integer"
    NUMBER = "number"
    # A share from 0 to 1, shown as a percentage.
    PERCENT = "percent"


@dataclass(frozen=True)
class Column:
    label: str
    kind: Kind = Kind.TEXT


@dataclass
class Section:
    title: str
    columns: list[Column]
    rows: list[list[Cell]]
    # A sentence under the title: how to read the table.
    note: str = ""


@dataclass
class ReportDoc:
    key: str
    title: str
    # How the report was made, as label and value: the method and its definition, the framework,
    # the version, the time. ``method`` and ``made_on`` are repeated on every sheet and page.
    about: list[tuple[str, str]]
    method: str
    made_on: datetime
    sections: list[Section] = field(default_factory=list)

    @property
    def stamp(self) -> str:
        return f"{self.method} · made {self.made_on.strftime('%Y-%m-%d %H:%M')} UTC"


def shown(value: Cell, kind: Kind) -> str:
    """A cell as text, for the PDF and for screens that do not format numbers themselves."""
    if value is None:
        return ""
    if kind is Kind.PERCENT and isinstance(value, int | float):
        return f"{round(value * 100)}%"
    if kind is Kind.NUMBER and isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


# --- Excel ---------------------------------------------------------------------------------


def _text_cell(sheet, row: int, column: int, value: str) -> None:  # type: ignore[no-untyped-def]
    cell = sheet.cell(row=row, column=column)
    cell.value = value
    # A value that starts like a formula stays text.
    cell.data_type = "s"
    cell.alignment = Alignment(wrap_text=True, vertical="top")


def _sheet_title(title: str, used: set[str]) -> str:
    name = _BAD_SHEET.sub(" ", title).strip()[:SHEET_NAME_MAX] or "Sheet"
    base, n = name, 2
    while name.casefold() in used:
        suffix = f" {n}"
        name = base[: SHEET_NAME_MAX - len(suffix)] + suffix
        n += 1
    used.add(name.casefold())
    return name


def to_xlsx(doc: ReportDoc) -> bytes:
    """The report as a workbook: an About sheet, then one sheet for each table, each sheet
    starting with the title, the method and the time it was made."""
    book = Workbook()
    about = book.active
    assert about is not None
    used: set[str] = set()
    about.title = _sheet_title("About", used)
    about.column_dimensions["A"].width = 24
    about.column_dimensions["B"].width = 110
    _text_cell(about, 1, 1, doc.title)
    about["A1"].font = Font(bold=True, size=14)
    for index, (label, value) in enumerate(doc.about, start=3):
        _text_cell(about, index, 1, label)
        about.cell(row=index, column=1).font = Font(bold=True)
        _text_cell(about, index, 2, value)

    head = PatternFill("solid", start_color="1F6F6B")
    for section in doc.sections:
        sheet = book.create_sheet(_sheet_title(section.title, used))
        _text_cell(sheet, 1, 1, f"{doc.title}: {section.title}")
        sheet["A1"].font = Font(bold=True, size=13)
        _text_cell(sheet, 2, 1, f"Method: {doc.method}")
        _text_cell(sheet, 3, 1, f"Made on: {doc.made_on.strftime('%Y-%m-%d %H:%M')} UTC")
        header_row = 4
        if section.note:
            _text_cell(sheet, 4, 1, section.note)
            header_row = 5
        for c, column in enumerate(section.columns, start=1):
            _text_cell(sheet, header_row, c, column.label)
            cell = sheet.cell(row=header_row, column=c)
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = head
        for r, row in enumerate(section.rows[:MAX_ROWS], start=header_row + 1):
            for c, (column, item) in enumerate(zip(section.columns, row, strict=False), start=1):
                if item is None:
                    continue
                if isinstance(item, str):
                    _text_cell(sheet, r, c, item)
                    continue
                cell = sheet.cell(row=r, column=c, value=item)
                if column.kind is Kind.PERCENT:
                    cell.number_format = "0%"
                elif column.kind is Kind.NUMBER:
                    cell.number_format = "0.00"
        sheet.freeze_panes = sheet.cell(row=header_row + 1, column=1)
        for c, column in enumerate(section.columns, start=1):
            longest = max(
                [len(column.label)]
                + [
                    len(shown(row[c - 1], column.kind))
                    for row in section.rows[:200]
                    if c <= len(row)
                ]
            )
            sheet.column_dimensions[get_column_letter(c)].width = min(max(12, longest + 2), 70)
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()


# --- PDF -----------------------------------------------------------------------------------


def _drawable(value: str) -> str:
    """Text limited to what the built-in PDF font can draw."""
    return value.encode("cp1252", "replace").decode("cp1252")


def _pdf_text(value: str) -> str:
    """Drawable text, escaped for the paragraph markup."""
    return escape(_drawable(value))


def to_pdf(doc: ReportDoc) -> bytes:
    """The report as a PDF (A4 landscape) with the method and the time it was made in the footer
    of every page."""
    styles = getSampleStyleSheet()
    body = ParagraphStyle("body", parent=styles["BodyText"], fontSize=8.5, leading=10.5)
    head = ParagraphStyle("head", parent=body, textColor=colors.white, fontName="Helvetica-Bold")
    title = ParagraphStyle("title", parent=styles["Title"], alignment=0, fontSize=17)
    heading = ParagraphStyle("heading", parent=styles["Heading2"], fontSize=12.5, spaceBefore=10)
    out = io.BytesIO()
    page = landscape(A4)
    margin = 14 * mm
    width = page[0] - 2 * margin
    footer = _drawable(f"{doc.title} — {doc.stamp}")

    def stamp(canvas, document) -> None:  # type: ignore[no-untyped-def]
        canvas.saveState()
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(colors.grey)
        canvas.drawString(margin, 8 * mm, footer)
        canvas.drawRightString(page[0] - margin, 8 * mm, f"Page {document.page}")
        canvas.restoreState()

    story: list[Any] = [Paragraph(_pdf_text(doc.title), title)]
    for label, value in doc.about:
        story.append(Paragraph(f"<b>{_pdf_text(label)}:</b> {_pdf_text(value)}", body))
    for section in doc.sections:
        story.append(Paragraph(_pdf_text(section.title), heading))
        if section.note:
            story.append(Paragraph(_pdf_text(section.note), body))
            story.append(Spacer(1, 2 * mm))
        if not section.columns:
            continue
        lengths = [
            max(
                [len(c.label)]
                + [len(shown(row[i], c.kind)) for row in section.rows[:100] if i < len(row)]
            )
            for i, c in enumerate(section.columns)
        ]
        weights = [min(max(w, 6), 60) for w in lengths]
        scale = width / sum(weights)
        data = [[Paragraph(_pdf_text(c.label), head) for c in section.columns]]
        for row in section.rows[:MAX_ROWS]:
            data.append(
                [
                    Paragraph(_pdf_text(shown(value, c.kind)), body)
                    for c, value in zip(section.columns, row, strict=False)
                ]
            )
        if len(data) == 1:
            story.append(Paragraph("None.", body))
            continue
        table = Table(data, colWidths=[w * scale for w in weights], repeatRows=1)
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F6F6B")),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#B8C4C6")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    (
                        "ROWBACKGROUNDS",
                        (0, 1),
                        (-1, -1),
                        [colors.white, colors.HexColor("#F2F6F6")],
                    ),
                ]
            )
        )
        story.append(table)
    SimpleDocTemplate(
        out,
        pagesize=page,
        leftMargin=margin,
        rightMargin=margin,
        topMargin=margin,
        bottomMargin=16 * mm,
        title=doc.title,
        author="Curriculum in Context",
    ).build(story, onFirstPage=stamp, onLaterPages=stamp)
    return out.getvalue()
