"""Upload screening and the isolated extraction worker, using synthetic documents."""

import os

import pytest

from app.services import extraction
from app.services.extraction import UploadRejected, detect_type, extract, safe_file_name
from tests import samples


# ----- type detection (content first, extension must agree) -----------------------------------
@pytest.mark.parametrize(
    ("name", "data", "expected"),
    [
        ("hours.pdf", b"%PDF-1.7 ...", "pdf"),
        ("FAQ.DOCX", b"PK\x03\x04...", "docx"),
        ("notes.txt", b"plain", "text"),
        ("notes.md", b"# heading", "text"),
    ],
)
def test_detect_type_from_content(name, data, expected):
    assert detect_type(name, data) == expected


@pytest.mark.parametrize(
    ("name", "data", "code"),
    [
        ("invoice.pdf", b"PK\x03\x04zip", "type_mismatch"),  # zip disguised as PDF
        ("report.docx", b"%PDF-1.7", "type_mismatch"),
        ("notes.txt", b"%PDF-1.7", "type_mismatch"),
        ("payload.exe", b"MZ\x90\x00", "unsupported_type"),
        ("page.html", b"<html><script>", "unsupported_type"),
        ("image.png", b"\x89PNG\r\n", "unsupported_type"),
        ("macro.docm", b"PK\x03\x04", "unsupported_type"),
        ("empty.txt", b"", "empty"),
        ("big.txt", b"a" * (10 * 1024 * 1024 + 1), "too_large"),
    ],
    ids=[
        "zip-as-pdf",
        "pdf-as-docx",
        "pdf-as-txt",
        "exe",
        "html",
        "png",
        "docm",
        "empty",
        "too-large",
    ],
)
def test_detect_type_rejections(name, data, code):
    with pytest.raises(UploadRejected) as info:
        detect_type(name, data)
    assert info.value.code == code
    assert info.value.message


def test_safe_file_name_is_display_only():
    assert safe_file_name("C:\\Users\\x\\..\\Price list.pdf") == "Price list.pdf"
    assert safe_file_name("../../etc/passwd") == "passwd"
    assert safe_file_name("evil\u202egpj.pdf") == "evilgpj.pdf"
    assert safe_file_name("") == "document"
    assert len(safe_file_name("a" * 500 + ".pdf")) == 200


# ----- worker: real parsing in a child process ------------------------------------------------
def test_pdf_text_is_extracted():
    result = extract("pdf", samples.pdf("Walk-ins welcome from 8am"))
    assert "Walk-ins welcome from 8am" in result.text
    assert result.page_count == 1


def test_harmless_pdf_open_action_is_allowed():
    assert "opening hours" in extract("pdf", samples.pdf_with_page_destination()).text


def test_docx_paragraphs_and_tables_are_extracted():
    data = samples.docx(
        "Opening hours",
        "Monday to Friday",
        table=[["Service", "Price"], ["Eye exam", "NGN 15,000"]],
    )
    text = extract("docx", data).text
    assert "Monday to Friday" in text
    assert "Eye exam | NGN 15,000" in text


def test_text_is_cleaned():
    raw = "\ufeffLine one\r\n\r\n\r\n\r\nLine\ttwo\x07\u202e  \n"
    assert extract("text", raw.encode()).text == "Line one\n\nLine two"


@pytest.mark.parametrize(
    ("kind", "build", "code"),
    [
        ("pdf", samples.pdf_with_javascript, "active_content"),
        ("pdf", samples.pdf_with_document_javascript, "active_content"),
        ("pdf", samples.pdf_with_launch_action, "active_content"),
        ("pdf", samples.pdf_with_attachment, "embedded_files"),
        ("pdf", samples.pdf_encrypted, "encrypted"),
        ("pdf", samples.pdf_blank, "no_text"),
        ("pdf", lambda: b"%PDF-1.4\nnot really a pdf", "malformed"),
        ("docx", samples.docx_with_macros, "macros"),
        ("docx", samples.docx_with_embedding, "embedded_files"),
        ("docx", samples.docx_zip_bomb, "too_complex"),
        ("docx", lambda: b"PK\x03\x04 truncated", "malformed"),
        ("text", lambda: "caf\u00e9".encode("latin-1"), "unsupported_encoding"),
        ("text", lambda: b"bin\x00ary", "unsupported_encoding"),
        ("text", lambda: b"   \n\n  ", "no_text"),
        ("text", lambda: b"x" * 300_001, "too_long"),
    ],
    ids=[
        "pdf-openaction-js",
        "pdf-document-js",
        "pdf-launch",
        "pdf-attachment",
        "pdf-encrypted",
        "pdf-no-text",
        "pdf-malformed",
        "docx-macros",
        "docx-embedding",
        "docx-zip-bomb",
        "docx-truncated",
        "text-latin1",
        "text-nul",
        "text-blank",
        "text-too-long",
    ],
)
def test_dangerous_or_unusable_documents_are_rejected(kind, build, code):
    with pytest.raises(UploadRejected) as info:
        extract(kind, build())
    assert info.value.code == code


def test_worker_receives_no_secrets(monkeypatch):
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "sb_secret_should_not_leak")
    env = extraction._worker_env()
    assert "SUPABASE_SECRET_KEY" not in env
    assert set(env) <= {"SYSTEMROOT"}


def test_worker_timeout_is_enforced(monkeypatch):
    monkeypatch.setattr(extraction, "EXTRACTION_TIMEOUT_SECONDS", 0.001)
    with pytest.raises(UploadRejected) as info:
        extract("text", b"hello")
    assert info.value.code == "timeout"


@pytest.mark.skipif(os.name == "nt", reason="POSIX resource limits apply in Docker/CI only")
def test_worker_memory_limit_is_applied():
    import subprocess
    import sys

    probe = (
        "import resource, runpy; "
        f"m = runpy.run_path({str(extraction.WORKER)!r}); "
        "m['_limit_resources'](); print(resource.getrlimit(resource.RLIMIT_AS)[0])"
    )
    out = subprocess.run(  # noqa: S603 - fixed interpreter and probe
        [sys.executable, "-I", "-c", probe],
        capture_output=True,
        text=True,
        check=True,
    )
    assert int(out.stdout.strip()) == 768 * 1024 * 1024
