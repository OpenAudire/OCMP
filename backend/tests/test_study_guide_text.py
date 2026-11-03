"""Tests for reading the text of an uploaded study guide (ADR 047): kinds, limits, refusals."""

import io
import zipfile

import pytest
from pypdf import PdfReader, PdfWriter

from app.services import study_guide_text as reading
from app.services.authorization import InvalidRequestError
from tests.study_guide_helpers import OUTCOMES, guide_lines, make_docx, make_pdf


class TestKind:
    def test_a_pdf_and_a_word_file_are_known_by_their_first_bytes(self) -> None:
        assert reading.kind_of(make_pdf()) == "pdf"
        assert reading.kind_of(make_docx()) == "docx"

    @pytest.mark.parametrize("content", [b"", b"hello", b"\x89PNG\r\n\x1a\n", b"<html></html>"])
    def test_anything_else_is_refused(self, content: bytes) -> None:
        with pytest.raises(InvalidRequestError, match="PDF or a Word"):
            reading.kind_of(content)


class TestReading:
    def test_the_text_of_a_word_file(self) -> None:
        guide = reading.read_guide(make_docx())

        text = "\n".join(guide.chunks)
        assert all(outcome in text for outcome in OUTCOMES)
        assert not guide.truncated and guide.characters > 200

    def test_the_text_of_a_pdf(self) -> None:
        guide = reading.read_guide(make_pdf())

        text = "\n".join(guide.chunks)
        assert all(outcome in text for outcome in OUTCOMES)

    def test_table_cells_are_read_too(self) -> None:
        from docx import Document

        document = Document()
        for line in guide_lines([]):
            document.add_paragraph(line)
        table = document.add_table(rows=1, cols=2)
        table.rows[0].cells[0].text = "Outcome 1"
        table.rows[0].cells[1].text = "Describe the heart."
        out = io.BytesIO()
        document.save(out)

        text = "\n".join(reading.read_guide(out.getvalue()).chunks)

        assert "Outcome 1 | Describe the heart." in text

    def test_a_file_that_is_too_large_is_refused_before_it_is_read(self) -> None:
        content = b"%PDF-" + b"0" * reading.MAX_UPLOAD_BYTES
        with pytest.raises(InvalidRequestError, match="larger than 10 MB"):
            reading.read_guide(content)

    def test_a_pdf_with_a_password_is_refused(self) -> None:
        writer = PdfWriter(clone_from=PdfReader(io.BytesIO(make_pdf())))
        writer.encrypt("secret")
        out = io.BytesIO()
        writer.write(out)

        with pytest.raises(InvalidRequestError, match="password"):
            reading.read_guide(out.getvalue())

    def test_a_scan_without_text_is_refused_with_the_reason(self) -> None:
        writer = PdfWriter()
        writer.add_blank_page(width=612, height=792)
        out = io.BytesIO()
        writer.write(out)

        with pytest.raises(InvalidRequestError, match="no text recognition"):
            reading.read_guide(out.getvalue())

    def test_a_pdf_with_too_many_pages_is_refused(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(reading, "MAX_PDF_PAGES", 0)
        with pytest.raises(InvalidRequestError, match="more than 0 pages"):
            reading.read_guide(make_pdf())

    @pytest.mark.parametrize("content", [b"%PDF-1.4 this is not a pdf", b"PK\x03\x04 nope"])
    def test_a_damaged_file_is_refused(self, content: bytes) -> None:
        with pytest.raises(InvalidRequestError, match="could not be read"):
            reading.read_guide(content)

    def test_a_zip_that_unpacks_to_too_much_is_refused_without_unpacking_it(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(reading, "MAX_UNPACKED_BYTES", 1_000)
        out = io.BytesIO()
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("word/document.xml", "a" * 5_000)

        with pytest.raises(InvalidRequestError, match="too large once unpacked"):
            reading.read_guide(out.getvalue())

    def test_a_zip_that_is_not_a_word_file_is_refused(self) -> None:
        out = io.BytesIO()
        with zipfile.ZipFile(out, "w") as archive:
            archive.writestr("notes.txt", "hello " * 100)

        with pytest.raises(InvalidRequestError, match="PDF or a Word"):
            reading.read_guide(out.getvalue())

    def test_the_file_name_is_never_part_of_what_is_read(self) -> None:
        # read_guide takes bytes only: there is no way to hand it a name.
        import inspect

        assert list(inspect.signature(reading.read_guide).parameters) == ["content"]


class TestChunks:
    def test_short_text_is_one_piece(self) -> None:
        assert reading.chunks_of("one\ntwo") == (["one\ntwo"], False)

    def test_long_text_is_cut_at_line_ends_into_pieces_that_fit(self) -> None:
        line = "x" * 1_000
        text = "\n".join([line] * 30)

        pieces, truncated = reading.chunks_of(text)

        assert len(pieces) == 3 and not truncated
        assert all(len(piece) <= reading.CHUNK_CHARS for piece in pieces)
        assert "".join(pieces).replace("\n", "") == line * 30

    def test_one_very_long_line_is_cut(self) -> None:
        pieces, _ = reading.chunks_of("y" * (reading.CHUNK_CHARS * 2 + 5))
        assert [len(p) for p in pieces] == [reading.CHUNK_CHARS, reading.CHUNK_CHARS, 5]

    def test_only_the_first_pieces_are_kept_and_it_says_so(self) -> None:
        text = "\n".join(["z" * 10_000] * (reading.MAX_CHUNKS + 3))
        pieces, truncated = reading.chunks_of(text)
        assert len(pieces) == reading.MAX_CHUNKS and truncated
