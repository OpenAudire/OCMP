"""Reading the text of an uploaded study guide (Slice 1.18, ADR 047).

The file is untrusted. Its kind is decided from its first bytes, never from its name (the name is
never read: it can carry a person's name), and every limit is checked before the content is
unpacked: the size of the upload, the pages of a PDF, the unpacked size of a Word file and the
amount of text. Encrypted PDFs and documents without text (scans: there is no OCR) are refused
with a reason. Nothing here touches the database or the network, and nothing is written to disk.
"""

import io
import re
import zipfile
from dataclasses import dataclass

from app.services.authorization import InvalidRequestError

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_PDF_PAGES = 200
# A .docx is a zip file; refuse one that unpacks to more than this (a "zip bomb").
MAX_UNPACKED_BYTES = 60 * 1024 * 1024
MAX_UNPACKED_FILES = 2_000
MAX_TEXT_CHARS = 400_000
MIN_TEXT_CHARS = 200
# The text is read in pieces of about this size, one AI call each (the guard allows 60 000).
CHUNK_CHARS = 12_000
MAX_CHUNKS = 8

_SPACE = re.compile(r"[ \t\r\f\v]+")
_BLANKS = re.compile(r"\n{3,}")


@dataclass(frozen=True)
class GuideText:
    """What was read: the pieces to send, and whether the end of a long guide was left out."""

    chunks: list[str]
    truncated: bool
    characters: int


def kind_of(content: bytes) -> str:
    """``pdf`` or ``docx`` from the first bytes.

    Raises:
        InvalidRequestError: For anything else.
    """
    if content.startswith(b"%PDF-"):
        return "pdf"
    if content.startswith(b"PK\x03\x04"):
        return "docx"
    raise InvalidRequestError("Upload a PDF or a Word (.docx) file.")


def _clean(text: str) -> str:
    lines = [_SPACE.sub(" ", line).strip() for line in text.replace("\x00", "").splitlines()]
    return _BLANKS.sub("\n\n", "\n".join(lines)).strip()


def _pdf_text(content: bytes) -> str:
    from pypdf import PdfReader
    from pypdf.errors import PyPdfError

    try:
        reader = PdfReader(io.BytesIO(content), strict=False)
        if reader.is_encrypted:
            raise InvalidRequestError("This PDF is protected with a password. Remove it first.")
        if len(reader.pages) > MAX_PDF_PAGES:
            raise InvalidRequestError(
                f"This PDF has more than {MAX_PDF_PAGES} pages. Upload one module's guide."
            )
        parts: list[str] = []
        total = 0
        for page in reader.pages:
            piece = page.extract_text() or ""
            parts.append(piece)
            total += len(piece)
            if total > MAX_TEXT_CHARS:
                break
        return "\n\n".join(parts)
    except InvalidRequestError:
        raise
    except (PyPdfError, ValueError, KeyError, TypeError, RecursionError, OSError):
        raise InvalidRequestError("This PDF could not be read. Is it damaged?") from None


def _docx_text(content: bytes) -> str:
    from docx import Document

    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            members = archive.infolist()
            if len(members) > MAX_UNPACKED_FILES or (
                sum(member.file_size for member in members) > MAX_UNPACKED_BYTES
            ):
                raise InvalidRequestError("This Word file is too large once unpacked.")
            if "word/document.xml" not in {member.filename for member in members}:
                raise InvalidRequestError("Upload a PDF or a Word (.docx) file.")
        document = Document(io.BytesIO(content))
        parts = [paragraph.text for paragraph in document.paragraphs]
        for table in document.tables:
            for row in table.rows:
                parts.append(" | ".join(cell.text.strip() for cell in row.cells))
        return "\n".join(parts)
    except InvalidRequestError:
        raise
    except (zipfile.BadZipFile, ValueError, KeyError, TypeError, OSError):
        raise InvalidRequestError("This Word file could not be read. Is it damaged?") from None


def chunks_of(text: str) -> tuple[list[str], bool]:
    """Pieces of about ``CHUNK_CHARS``, cut at line ends, at most ``MAX_CHUNKS`` of them.

    The second value says that the end of the text did not fit and was left out.
    """
    pieces: list[str] = []
    current: list[str] = []
    size = 0
    for line in text.split("\n"):
        # A single very long line is cut so that no piece goes over the limit.
        while len(line) > CHUNK_CHARS:
            head, line = line[:CHUNK_CHARS], line[CHUNK_CHARS:]
            if current:
                pieces.append("\n".join(current))
                current, size = [], 0
            pieces.append(head)
        if size + len(line) + 1 > CHUNK_CHARS and current:
            pieces.append("\n".join(current))
            current, size = [], 0
        current.append(line)
        size += len(line) + 1
    if current:
        pieces.append("\n".join(current))
    pieces = [piece.strip() for piece in pieces if piece.strip()]
    return pieces[:MAX_CHUNKS], len(pieces) > MAX_CHUNKS


def read_guide(content: bytes) -> GuideText:
    """The pieces of text in a PDF or Word file.

    Raises:
        InvalidRequestError: Too large, not a PDF or Word file, protected, damaged, or without
            enough text to read (a scan).
    """
    if len(content) > MAX_UPLOAD_BYTES:
        raise InvalidRequestError("The file is larger than 10 MB.")
    kind = kind_of(content)
    raw = _pdf_text(content) if kind == "pdf" else _docx_text(content)
    text = _clean(raw)[:MAX_TEXT_CHARS]
    if len(text) < MIN_TEXT_CHARS:
        raise InvalidRequestError(
            "Almost no text could be read from this file. Scanned documents are not supported "
            "because there is no text recognition."
        )
    chunks, truncated = chunks_of(text)
    return GuideText(chunks=chunks, truncated=truncated, characters=len(text))
