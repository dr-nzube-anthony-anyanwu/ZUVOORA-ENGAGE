"""Isolated document text extractor (Phase 2c, ADR-023).

Run ONLY as a child process: `python -I extract_worker.py <pdf|docx|text|image> <vision_pages>`
with the file on stdin. It prints exactly one JSON object on stdout and never raises:
{"ok": true, "text": ..., "page_count": n}, {"ok": true, "images": [...], "page_count": n} or
{"ok": false, "error": "<code>"}.

Images (Phase 3g, ADR-041): photos and scanned PDF pages are decoded with Pillow / rendered with
PDFium, size-limited and re-encoded as fresh JPEGs. Re-encoding drops EXIF/GPS and all other
metadata; only pixels leave this process, for an AI model to read. `vision_pages` (0 = AI reading
not allowed) caps how many pages may be returned as images.

It imports nothing from the application, receives no environment variables (so no secrets), has
no database access, and on POSIX applies memory/CPU/file limits to itself before parsing.
"""

from __future__ import annotations

import base64
import io
import json
import re
import sys
import unicodedata
import warnings
import zipfile

MAX_TEXT_CHARS = 300_000
MAX_IMAGE_PIXELS = 40_000_000  # larger images are refused (decompression bombs)
MAX_IMAGE_SIDE = 1600  # long side sent to the model, in pixels
RENDER_DPI = 150
JPEG_QUALITY = 85
MIN_CHARS_PER_PAGE = 20  # less selectable text than this means the PDF is a scan
MAX_PDF_PAGES = 300
MAX_ZIP_ENTRIES = 1_000
MAX_ZIP_UNCOMPRESSED = 50 * 1024 * 1024
MAX_ZIP_RATIO = 200
MEMORY_LIMIT = 768 * 1024 * 1024
CPU_SECONDS = 30

_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f  ‪-‮⁦-⁩]")
_BLANK_RUNS = re.compile(r"\n{3,}")
_TRAILING_SPACE = re.compile(r"[ \t]+\n")

# PDF features that execute code, launch programs or carry hidden payloads.
_ACTIVE_ACTIONS = {"/JavaScript", "/Launch", "/ImportData", "/SubmitForm", "/Rendition", "/GoToE"}


class Rejected(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _limit_resources() -> None:
    try:
        import resource  # POSIX only
    except ImportError:  # Windows development: the parent's timeout still applies
        return
    resource.setrlimit(resource.RLIMIT_AS, (MEMORY_LIMIT, MEMORY_LIMIT))
    resource.setrlimit(resource.RLIMIT_CPU, (CPU_SECONDS, CPU_SECONDS))
    resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))  # may not write files
    resource.setrlimit(resource.RLIMIT_NOFILE, (32, 32))


def _clean(text: str) -> str:
    text = unicodedata.normalize("NFC", text).replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\t", " ").replace(" ", " ")
    text = _CONTROL.sub("", text)
    text = _TRAILING_SPACE.sub("\n", text)
    return _BLANK_RUNS.sub("\n\n", text).strip()


# ----- PDF ----------------------------------------------------------------------------------------
def _action_is_active(action) -> bool:
    try:
        action = action.get_object()
    except Exception:  # noqa: BLE001 - unreadable action: treat as suspicious
        return True
    if not hasattr(action, "get"):
        return False  # e.g. a destination array (go to page) is harmless
    if action.get("/S") in _ACTIVE_ACTIONS:
        return True
    nxt = action.get("/Next")
    if nxt is None:
        return False
    items = nxt if isinstance(nxt, list) else [nxt]
    return any(_action_is_active(item) for item in items)


def _pdf(data: bytes) -> tuple[str, int]:
    from pypdf import PdfReader

    try:
        reader = PdfReader(io.BytesIO(data), strict=False)
        if reader.is_encrypted:
            raise Rejected("encrypted")
        root = reader.trailer["/Root"].get_object()
        names = root.get("/Names")
        names = names.get_object() if names is not None else {}
        if "/EmbeddedFiles" in names:
            raise Rejected("embedded_files")
        if "/JavaScript" in names or "/AA" in root:
            raise Rejected("active_content")
        if "/OpenAction" in root and _action_is_active(root["/OpenAction"]):
            raise Rejected("active_content")
        acroform = root.get("/AcroForm")
        if acroform is not None and "/XFA" in acroform.get_object():
            raise Rejected("active_content")
        page_count = len(reader.pages)
        if page_count > MAX_PDF_PAGES:
            raise Rejected("too_complex")
        parts: list[str] = []
        size = 0
        for page in reader.pages:
            if "/AA" in page:
                raise Rejected("active_content")
            for annot in page.get("/Annots") or []:
                annot = annot.get_object()
                if annot.get("/Subtype") == "/FileAttachment":
                    raise Rejected("embedded_files")
                if "/A" in annot and _action_is_active(annot["/A"]):
                    raise Rejected("active_content")
            text = page.extract_text() or ""
            size += len(text)
            if size > MAX_TEXT_CHARS * 2:
                raise Rejected("too_long")
            parts.append(text)
    except Rejected:
        raise
    except RecursionError as exc:
        raise Rejected("too_complex") from exc
    except Exception as exc:  # noqa: BLE001 - any parser failure is a malformed file
        raise Rejected("malformed") from exc
    return "\n\n".join(parts), page_count


# ----- DOCX ---------------------------------------------------------------------------------------
def _docx(data: bytes) -> tuple[str, int]:
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
        infos = archive.infolist()
    except zipfile.BadZipFile as exc:
        raise Rejected("malformed") from exc
    if len(infos) > MAX_ZIP_ENTRIES:
        raise Rejected("too_complex")
    total = 0
    for info in infos:
        total += info.file_size
        if info.compress_size and info.file_size / info.compress_size > MAX_ZIP_RATIO:
            raise Rejected("too_complex")
    if total > MAX_ZIP_UNCOMPRESSED:
        raise Rejected("too_complex")
    names = {info.filename.lower() for info in infos}
    if "word/document.xml" not in names:
        raise Rejected("malformed")
    if any(n.endswith("vbaproject.bin") or n.endswith("vbadata.xml") for n in names):
        raise Rejected("macros")
    if any(n.startswith(("word/embeddings/", "word/activex/")) for n in names):
        raise Rejected("embedded_files")

    from docx import Document

    try:
        document = Document(io.BytesIO(data))
        parts = [p.text for p in document.paragraphs]
        for table in document.tables:
            for row in table.rows:
                cells: list[str] = []
                for cell in row.cells:
                    if cell.text not in cells:  # merged cells repeat their text
                        cells.append(cell.text)
                parts.append(" | ".join(cells))
    except Exception as exc:  # noqa: BLE001
        raise Rejected("malformed") from exc
    return "\n".join(parts), 0


# ----- plain text / Markdown ----------------------------------------------------------------------
def _text(data: bytes) -> tuple[str, int]:
    if b"\x00" in data:
        raise Rejected("unsupported_encoding")
    try:
        return data.decode("utf-8-sig"), 0
    except UnicodeDecodeError as exc:
        raise Rejected("unsupported_encoding") from exc


EXTRACTORS = {"pdf": _pdf, "docx": _docx, "text": _text}


# ----- images (photos and scanned pages) -----------------------------------------------------
def _to_jpeg(image) -> str:
    """Fresh JPEG of the pixels only (no EXIF/GPS/ICC/comments), long side ≤ MAX_IMAGE_SIDE."""
    from PIL import Image, ImageOps

    image = ImageOps.exif_transpose(image)  # apply camera rotation before the metadata is dropped
    if image.mode in ("RGBA", "LA", "P"):
        image = image.convert("RGBA")
        background = Image.new("RGB", image.size, "white")
        background.paste(image, mask=image.getchannel("A"))
        image = background
    elif image.mode != "RGB":
        image = image.convert("RGB")
    image.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE))
    clean = Image.new("RGB", image.size)
    clean.paste(image)  # a new image carries no metadata from the original
    buffer = io.BytesIO()
    clean.save(buffer, "JPEG", quality=JPEG_QUALITY, optimize=True)
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def _image(data: bytes) -> list[str]:
    from PIL import Image

    Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data), formats=["PNG", "JPEG", "WEBP"]) as probe:
                probe.verify()  # structural check; the image must be reopened afterwards
            with Image.open(io.BytesIO(data), formats=["PNG", "JPEG", "WEBP"]) as image:
                if image.width * image.height > MAX_IMAGE_PIXELS:
                    raise Rejected("too_complex")
                image.seek(0)  # animated files: first frame only
                image.load()
                return [_to_jpeg(image)]
    except Rejected:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise Rejected("too_complex") from exc
    except Exception as exc:  # noqa: BLE001 - any decoder failure is a malformed file
        raise Rejected("malformed") from exc


def _render_pdf(data: bytes, page_count: int, max_pages: int) -> list[str]:
    if page_count > max_pages:
        raise Rejected("scan_too_long")
    import pypdfium2 as pdfium

    try:
        document = pdfium.PdfDocument(data)
        images = []
        for index in range(len(document)):
            page = document[index]
            width, height = page.get_size()  # points (1/72 inch)
            scale = min(RENDER_DPI / 72, MAX_IMAGE_SIDE / max(width, height, 1))
            if width * scale * height * scale > MAX_IMAGE_PIXELS:
                raise Rejected("too_complex")
            images.append(_to_jpeg(page.render(scale=scale).to_pil()))
        return images
    except Rejected:
        raise
    except Exception as exc:  # noqa: BLE001
        raise Rejected("malformed") from exc


def _is_scan(text: str, pages: int) -> bool:
    return len(text) < MIN_CHARS_PER_PAGE * max(pages, 1)


def main() -> None:
    kind = sys.argv[1] if len(sys.argv) == 3 else ""
    try:
        vision_pages = int(sys.argv[2]) if len(sys.argv) == 3 else 0
        _limit_resources()
        data = sys.stdin.buffer.read()
        if kind == "image":
            if vision_pages < 1:
                raise Rejected("vision_unavailable")
            result = {"ok": True, "images": _image(data), "page_count": 1}
            sys.stdout.write(json.dumps(result))
            sys.stdout.flush()
            return
        extractor = EXTRACTORS.get(kind)
        if extractor is None:
            raise Rejected("extractor_failed")
        raw, pages = extractor(data)
        text = _clean(raw)
        if kind == "pdf" and vision_pages > 0 and _is_scan(text, pages):
            result = {"ok": True, "images": _render_pdf(data, pages, vision_pages),
                      "page_count": pages}
            sys.stdout.write(json.dumps(result))
            sys.stdout.flush()
            return
        if not text:
            raise Rejected("no_text")
        if len(text) > MAX_TEXT_CHARS:
            raise Rejected("too_long")
        result = {"ok": True, "text": text, "page_count": pages}
    except Rejected as exc:
        result = {"ok": False, "error": exc.code}
    except MemoryError:
        result = {"ok": False, "error": "too_complex"}
    except Exception:  # noqa: BLE001 - never leak tracebacks to the parent
        result = {"ok": False, "error": "extractor_failed"}
    sys.stdout.write(json.dumps(result))
    sys.stdout.flush()


if __name__ == "__main__":
    main()
