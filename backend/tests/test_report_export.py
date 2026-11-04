"""Tests for the report documents and their Excel and PDF export (ADR 051): no database."""

import io
from datetime import UTC, datetime

import pytest
from openpyxl import load_workbook
from pypdf import PdfReader

from app.services.report_export import (
    Column,
    Kind,
    ReportDoc,
    Section,
    shown,
    to_pdf,
    to_xlsx,
)

MADE = datetime(2026, 11, 4, 9, 42, tzinfo=UTC)


def doc(rows: list[list[object]] | None = None, **kw: object) -> ReportDoc:
    return ReportDoc(
        key="test",
        title=str(kw.pop("title", "Test report")),
        about=[("Method", "Single match. Covered with one link."), ("Framework", "Competencies")],
        method="Single match",
        made_on=MADE,
        sections=[
            Section(
                "Items",
                [
                    Column("Code"),
                    Column("Title"),
                    Column("Share", Kind.PERCENT),
                    Column("Links", Kind.INTEGER),
                ],
                rows if rows is not None else [["G1", "Clinical", 0.5, 3]],  # type: ignore[arg-type]
                note="How to read this table.",
            )
        ],
    )


class TestShown:
    def test_formats_by_kind(self) -> None:
        assert shown(0.6667, Kind.PERCENT) == "67%"
        assert shown(0.5, Kind.NUMBER) == "0.50"
        assert shown(3, Kind.INTEGER) == "3"
        assert shown(None, Kind.TEXT) == ""
        assert shown("x", Kind.TEXT) == "x"


class TestExcel:
    def test_has_an_about_sheet_and_a_sheet_per_table_each_stating_method_and_date(self) -> None:
        book = load_workbook(io.BytesIO(to_xlsx(doc())))

        assert book.sheetnames == ["About", "Items"]
        about = book["About"]
        assert about["A1"].value == "Test report"
        assert (about["A3"].value, about["B3"].value) == (
            "Method",
            "Single match. Covered with one link.",
        )
        items = book["Items"]
        assert items["A1"].value == "Test report: Items"
        assert items["A2"].value == "Method: Single match"
        assert items["A3"].value == "Made on: 2026-11-04 09:42 UTC"
        assert items["A4"].value == "How to read this table."
        assert [c.value for c in items[5]] == ["Code", "Title", "Share", "Links"]
        assert [c.value for c in items[6]] == ["G1", "Clinical", 0.5, 3]

    def test_percentages_are_numbers_with_a_percent_format(self) -> None:
        book = load_workbook(io.BytesIO(to_xlsx(doc())))

        share = book["Items"]["C6"]
        assert share.value == 0.5 and share.number_format == "0%"

    @pytest.mark.parametrize(
        "text", ['=HYPERLINK("http://evil","x")', "+1+1", "-2+3", "@SUM(A1)", "\t=1"]
    )
    def test_text_that_looks_like_a_formula_stays_text(self, text: str) -> None:
        book = load_workbook(io.BytesIO(to_xlsx(doc([[text, text, 0.1, 1]]))))

        cell = book["Items"]["A6"]
        assert cell.data_type == "s" and cell.value == text
        # The title and the About sheet are text too.
        evil = load_workbook(io.BytesIO(to_xlsx(doc(title="=1+1"))))
        assert evil["About"]["A1"].data_type == "s"

    def test_sheet_names_are_valid_and_unique(self) -> None:
        d = doc()
        d.sections = [
            Section("A/B: very long name that goes past thirty-one characters", [Column("x")], []),
            Section("A/B: very long name that goes past thirty-one characters", [Column("x")], []),
            Section("About", [Column("x")], []),
        ]

        names = load_workbook(io.BytesIO(to_xlsx(d))).sheetnames

        assert len(names) == len({n.casefold() for n in names}) == 4
        assert all(len(n) <= 31 and "/" not in n for n in names)

    def test_an_empty_table_still_has_its_heading_and_stamp(self) -> None:
        book = load_workbook(io.BytesIO(to_xlsx(doc([]))))

        assert book["Items"]["A2"].value == "Method: Single match"
        assert book["Items"].max_row == 5


class TestPdf:
    @staticmethod
    def pages(content: bytes) -> list[str]:
        return [page.extract_text() for page in PdfReader(io.BytesIO(content)).pages]

    def test_is_a_pdf_with_the_title_the_about_lines_and_the_table(self) -> None:
        content = to_pdf(doc())

        assert content.startswith(b"%PDF")
        text = self.pages(content)[0]
        for expected in ("Test report", "Framework: Competencies", "Items", "Clinical", "50%"):
            assert expected in text

    def test_every_page_states_the_method_and_the_date(self) -> None:
        rows = [[f"G{i}", f"Item number {i} " + "word " * 12, i / 400, i] for i in range(300)]

        pages = self.pages(to_pdf(doc(rows)))

        assert len(pages) > 3
        for number, text in enumerate(pages, start=1):
            assert "Single match · made 2026-11-04 09:42 UTC" in text.replace("\n", " ")
            assert f"Page {number}" in text

    def test_markup_and_symbols_in_text_do_not_break_it(self) -> None:
        nasty = (
            "<b>bold</b> & <script>x</script> 漢字 ë ê "
            + chr(0x2013)
            + " "
            + chr(0x2019)
            + "quoted"
            + chr(0x2019)
        )

        content = to_pdf(doc([["<para>", nasty, 0.1, 1]]))

        text = " ".join(self.pages(content))
        assert "<b>bold</b> & <script>x</script>" in text.replace("\n", " ")
        assert "ë ê" in text  # Western European letters are drawn
        assert "漢" not in text and "??" in text  # other scripts are replaced, not crashed on

    def test_an_empty_table_says_none(self) -> None:
        assert "None." in " ".join(self.pages(to_pdf(doc([]))))

    def test_a_title_with_markup_is_text(self) -> None:
        text = self.pages(to_pdf(doc(title="A <i>report</i> & more")))[0]

        assert "A <i>report</i> & more" in text.replace("\n", " ")
