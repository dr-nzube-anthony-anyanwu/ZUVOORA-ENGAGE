"""Synthetic test documents built in memory (no real clinic or patient data)."""

from __future__ import annotations

import io
import zipfile

from docx import Document
from pypdf import PdfReader, PdfWriter


def pdf(text: str = "Clinic opening hours are 8am to 5pm.", catalog_extra: bytes = b"") -> bytes:
    """A minimal one-page PDF with real, extractable text (optionally extra catalog entries)."""
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R " + catalog_extra + b" >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(out.tell())
        out.write(f"{number} 0 obj\n".encode() + body + b"\nendobj\n")
    xref = out.tell()
    out.write(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    for offset in offsets:
        out.write(f"{offset:010d} 00000 n \n".encode())
    out.write(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    )
    return out.getvalue()


def _rewrite(data: bytes, change) -> bytes:
    writer = PdfWriter(clone_from=PdfReader(io.BytesIO(data)))
    change(writer)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def pdf_with_javascript() -> bytes:
    """Runs JavaScript when opened (OpenAction)."""
    return pdf(catalog_extra=b"/OpenAction << /S /JavaScript /JS (app.alert(1)) >>")


def pdf_with_document_javascript() -> bytes:
    """Document-level JavaScript in the name tree."""
    return pdf(
        catalog_extra=b"/Names << /JavaScript << /Names [(x) << /S /JavaScript "
        b"/JS (app.alert(1)) >>] >> >>"
    )


def pdf_with_launch_action() -> bytes:
    return pdf(catalog_extra=b"/OpenAction << /S /Launch /F (cmd.exe) >>")


def pdf_with_page_destination() -> bytes:
    """A harmless OpenAction (go to page 1) that must still be accepted."""
    return pdf(catalog_extra=b"/OpenAction [3 0 R /Fit]")


def pdf_with_attachment() -> bytes:
    return _rewrite(pdf(), lambda w: w.add_attachment("payload.txt", b"hidden"))


def pdf_encrypted() -> bytes:
    return _rewrite(pdf(), lambda w: w.encrypt(user_password="secret-pw", algorithm="AES-128"))


def pdf_blank() -> bytes:
    def blank(writer: PdfWriter) -> None:
        writer.pages[0].replace_contents(None)  # no text at all (like a scanned image)

    return _rewrite(pdf(), blank)


def docx(*paragraphs: str, table: list[list[str]] | None = None) -> bytes:
    document = Document()
    for paragraph in paragraphs or ("We accept walk-in patients from 8am.",):
        document.add_paragraph(paragraph)
    if table:
        grid = document.add_table(rows=len(table), cols=len(table[0]))
        for r, row in enumerate(table):
            for c, value in enumerate(row):
                grid.cell(r, c).text = value
    out = io.BytesIO()
    document.save(out)
    return out.getvalue()


def _add_zip_entry(data: bytes, name: str, payload: bytes) -> bytes:
    source = zipfile.ZipFile(io.BytesIO(data))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as target:
        for item in source.infolist():
            target.writestr(item, source.read(item.filename))
        target.writestr(name, payload)
    return out.getvalue()


def docx_with_macros() -> bytes:
    return _add_zip_entry(docx(), "word/vbaProject.bin", b"\xd0\xcf\x11\xe0fake-vba")


def docx_with_embedding() -> bytes:
    return _add_zip_entry(docx(), "word/embeddings/oleObject1.bin", b"\xd0\xcf\x11\xe0ole")


def docx_zip_bomb() -> bytes:
    return _add_zip_entry(docx(), "word/media/bomb.bin", b"\0" * (60 * 1024 * 1024))
