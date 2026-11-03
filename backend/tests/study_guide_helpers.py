"""Small PDF and Word files for the study-guide tests, built in memory."""

import io

from docx import Document

OUTCOMES = [
    "Describe the structure of the heart and the cardiac cycle.",
    "Interpret a normal electrocardiogram trace.",
    "Explain how blood pressure is regulated.",
]


def guide_lines(outcomes: list[str] | None = None) -> list[str]:
    """Enough ordinary study-guide text to be read (over 200 characters)."""
    listed = outcomes if outcomes is not None else OUTCOMES
    return [
        "Cardiovascular Physiology: study guide",
        "This guide supports the cardiovascular block of the second year.",
        "Learning outcomes",
        "By the end of this module you will be able to:",
        *listed,
        "Assessment: one written paper and one practical examination.",
    ]


def make_docx(lines: list[str] | None = None) -> bytes:
    document = Document()
    for line in lines if lines is not None else guide_lines():
        document.add_paragraph(line)
    out = io.BytesIO()
    document.save(out)
    return out.getvalue()


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def make_pdf(lines: list[str] | None = None) -> bytes:
    """A one-page PDF with the lines as text (Helvetica, so plain ASCII)."""
    rows = lines if lines is not None else guide_lines()
    stream = (
        "BT /F1 12 Tf 14 TL 50 750 Td " + " ".join(f"({_escape(r)}) Tj T*" for r in rows) + " ET"
    )
    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        "/Resources << /Font << /F1 5 0 R >> >> >>",
        f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n{body}\nendobj\n".encode("latin-1")
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n"
    ).encode()
    return bytes(out)
