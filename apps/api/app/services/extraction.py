"""Upload screening and isolated text extraction for knowledge documents (Phase 2c, ADR-023).

The file type is decided from the file's own bytes; the name's extension must agree. The
declared MIME type is ignored. Parsing happens only in `extract_worker.py`, a separate process
with a timeout, no environment (no secrets) and, on POSIX, memory/CPU/file limits.
"""

from __future__ import annotations

import json
import os
import subprocess  # noqa: S404 - fixed interpreter + fixed script, no shell
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
EXTRACTION_TIMEOUT_SECONDS = 30
WORKER = Path(__file__).with_name("extract_worker.py")

DetectedType = Literal["pdf", "docx", "text", "image"]
_EXTENSIONS: dict[DetectedType, tuple[str, ...]] = {
    "pdf": (".pdf",),
    "docx": (".docx",),
    "text": (".txt", ".md", ".markdown"),
    "image": (".png", ".jpg", ".jpeg", ".webp"),
}

MESSAGES = {
    "unsupported_type": "Only PDF, Word (.docx), plain text (.txt), Markdown (.md) and image "
                        "(.png, .jpg, .webp) files can be uploaded.",
    "vision_unavailable": "Photos and scanned documents are read by AI, which is not available "
                          "for this clinic right now. Upload a document with selectable text.",
    "scan_too_long": "Scanned documents can have at most {pages} pages. Split the document into "
                     "smaller files.",
    "vision_failed": "The AI could not read this file right now. Please try again later.",
    "type_mismatch": "The file's contents do not match its extension.",
    "empty": "The file is empty.",
    "too_large": "Files can be at most 10 MB.",
    "no_text": "No text could be found. Scanned documents (images of text) are not supported; "
               "upload a document with selectable text.",
    "too_long": "The document contains too much text (limit 300,000 characters). Split it into "
                "smaller documents.",
    "encrypted": "Password-protected documents cannot be processed. Remove the password first.",
    "active_content": "The PDF contains scripts or automatic actions, which are not allowed.",
    "macros": "Documents with macros are not allowed.",
    "embedded_files": "Documents with embedded files or objects are not allowed.",
    "too_complex": "The document is too large or complex to process safely.",
    "malformed": "The file is damaged or not a valid document.",
    "timeout": "Processing took too long. Try a smaller or simpler document.",
    "unsupported_encoding": "Text files must be UTF-8 encoded.",
    "extractor_failed": "The document could not be processed.",
}


class UploadRejected(Exception):
    def __init__(self, code: str, **details: object) -> None:
        super().__init__(code)
        self.code = code
        self.message = MESSAGES.get(code, MESSAGES["extractor_failed"]).format(**details)


@dataclass(frozen=True)
class Extraction:
    """Text from the file, or page images (JPEG, base64) that an AI model must read first."""

    detected_type: DetectedType
    text: str
    page_count: int
    images: tuple[str, ...] = ()
    method: Literal["text", "vision"] = "text"


def safe_file_name(name: str | None) -> str:
    """Display-only file name: base name, no control characters, at most 200 characters."""
    base = (name or "").replace("\\", "/").rsplit("/", 1)[-1]
    base = unicodedata.normalize("NFC", base)
    base = "".join(ch for ch in base if unicodedata.category(ch)[0] != "C").strip(" .")
    return (base or "document")[:200]


def detect_type(file_name: str, data: bytes) -> DetectedType:
    if not data:
        raise UploadRejected("empty")
    if len(data) > MAX_UPLOAD_BYTES:
        raise UploadRejected("too_large")
    lower = file_name.lower()
    if data.startswith(b"%PDF-"):
        detected: DetectedType = "pdf"
    elif data.startswith(b"PK\x03\x04"):
        detected = "docx"  # the worker confirms the Word structure
    elif (data.startswith((b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff"))
          or (data[:4] == b"RIFF" and data[8:12] == b"WEBP")):
        detected = "image"  # the worker decodes it with an allow-list of formats
    elif lower.endswith(_EXTENSIONS["text"]):
        detected = "text"  # the worker requires valid UTF-8 without NUL bytes
    else:
        raise UploadRejected("unsupported_type")
    if not lower.endswith(_EXTENSIONS[detected]):
        if any(lower.endswith(ext) for exts in _EXTENSIONS.values() for ext in exts):
            raise UploadRejected("type_mismatch")
        raise UploadRejected("unsupported_type")
    return detected


def _worker_env() -> dict[str, str]:
    # Nothing from the API's environment (secrets) is passed on. Windows needs SYSTEMROOT.
    keep = ("SYSTEMROOT",) if os.name == "nt" else ()
    return {k: os.environ[k] for k in keep if k in os.environ}


def extract(detected_type: DetectedType, data: bytes, vision_pages: int = 0) -> Extraction:
    """Run the isolated worker. `vision_pages` > 0 allows photos and scanned PDFs (up to that many
    pages) to come back as images for AI reading; 0 keeps the text-only behaviour."""
    try:
        completed = subprocess.run(  # noqa: S603 - fixed argv, no shell, isolated interpreter
            [sys.executable, "-I", str(WORKER), detected_type, str(max(vision_pages, 0))],
            input=data,
            capture_output=True,
            timeout=EXTRACTION_TIMEOUT_SECONDS,
            env=_worker_env(),
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise UploadRejected("timeout") from exc
    try:
        result = json.loads(completed.stdout.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        # A negative return code means the OS killed the worker (e.g. a resource limit).
        code = "too_complex" if completed.returncode < 0 else "extractor_failed"
        raise UploadRejected(code) from exc
    if not result.get("ok"):
        raise UploadRejected(str(result.get("error", "extractor_failed")), pages=vision_pages)
    page_count = int(result.get("page_count") or 0)
    if "images" in result:
        images = tuple(str(i) for i in result["images"])
        if not images:
            raise UploadRejected("no_text")
        return Extraction(detected_type, "", page_count, images=images, method="vision")
    return Extraction(detected_type, result["text"], page_count)
