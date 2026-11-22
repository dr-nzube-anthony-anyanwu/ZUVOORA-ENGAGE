"""Phase 3g: photos and scanned PDFs — screening, the isolated worker, the gateway payload and the
vision reader. Synthetic images only; no real model calls."""

from __future__ import annotations

import base64
import io
import json
from decimal import Decimal

import httpx
import pytest
from PIL import Image, ImageDraw

from app.services.ai.gateway import (
    FakeGateway,
    ModelError,
    ModelResult,
    OpenRouterGateway,
    PriceCeiling,
)
from app.services.ai.vision import NO_TEXT, VisionReader, clean_transcription
from app.services.extraction import UploadRejected, detect_type, extract
from tests import samples

CEILING = PriceCeiling(Decimal("0.50"), Decimal("1.00"))


def picture(size=(1200, 800), fmt="PNG", **save) -> bytes:
    image = Image.new("RGB", size, "white")
    ImageDraw.Draw(image).text((40, 40), "Comprehensive eye exam 25,000", fill="black")
    buffer = io.BytesIO()
    image.save(buffer, fmt, **save)
    return buffer.getvalue()


def with_gps() -> bytes:
    exif = Image.Exif()
    exif[0x010F] = "PhoneMaker"  # camera make
    exif[0x8825] = {1: "N", 2: (6.0, 27.0, 0.0), 3: "E", 4: (3.0, 23.0, 0.0)}  # GPS
    return picture(fmt="JPEG", exif=exif)


def scanned_pdf(pages: int = 1) -> bytes:
    images = [Image.new("RGB", (1240, 1754), "white") for _ in range(pages)]
    for image in images:
        ImageDraw.Draw(image).text((60, 60), "Opening hours 8am - 5pm", fill="black")
    buffer = io.BytesIO()
    images[0].save(buffer, "PDF", save_all=True, append_images=images[1:])
    return buffer.getvalue()


def decoded(b64: str) -> Image.Image:
    return Image.open(io.BytesIO(base64.b64decode(b64)))


# ----- screening -----------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("name", "data"),
    [
        ("prices.png", picture()),
        ("flyer.JPG", picture(fmt="JPEG")),
        ("sign.jpeg", picture(fmt="JPEG")),
        ("leaflet.webp", picture(fmt="WEBP")),
    ],
)
def test_images_are_detected_from_their_bytes(name, data):
    assert detect_type(name, data) == "image"


@pytest.mark.parametrize(
    ("name", "data", "code"),
    [
        ("logo.svg", b"<svg xmlns='http://www.w3.org/2000/svg'><script/></svg>", "unsupported_type"),
        ("anim.gif", b"GIF89a....", "unsupported_type"),
        ("photo.heic", b"\x00\x00\x00\x18ftypheic", "unsupported_type"),
        ("prices.pdf", picture(), "type_mismatch"),  # PNG disguised as PDF
        ("prices.png", b"%PDF-1.7", "type_mismatch"),  # PDF disguised as PNG
    ],
)
def test_other_formats_and_disguises_are_rejected(name, data, code):
    with pytest.raises(UploadRejected) as info:
        detect_type(name, data)
    assert info.value.code == code


# ----- isolated worker -------------------------------------------------------------------------
def test_photo_is_reencoded_without_metadata_and_resized():
    data = with_gps()
    assert Image.open(io.BytesIO(data)).getexif()  # the upload really carries EXIF/GPS
    result = extract("image", data, 10)
    assert (result.method, result.page_count, result.text) == ("vision", 1, "")
    out = decoded(result.images[0])
    assert out.format == "JPEG" and max(out.size) <= 1600
    assert dict(out.getexif()) == {}
    assert not {"exif", "icc_profile", "comment", "xmp"} & set(out.info)
    assert b"PhoneMaker" not in base64.b64decode(result.images[0])


def test_transparent_png_is_flattened():
    image = Image.new("RGBA", (300, 200), (0, 0, 0, 0))
    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    out = decoded(extract("image", buffer.getvalue(), 10).images[0])
    assert out.mode == "RGB" and out.getpixel((10, 10)) == (255, 255, 255)


def test_decompression_bomb_is_rejected():
    bomb = picture(size=(9000, 9000), fmt="PNG")  # 81 MP, tiny file
    with pytest.raises(UploadRejected) as info:
        extract("image", bomb, 10)
    assert info.value.code == "too_complex"


def test_corrupt_image_is_rejected():
    with pytest.raises(UploadRejected) as info:
        extract("image", picture()[:200], 10)
    assert info.value.code == "malformed"


def test_photos_need_ai_reading():
    with pytest.raises(UploadRejected) as info:
        extract("image", picture(), 0)
    assert info.value.code == "vision_unavailable"


def test_scanned_pdf_is_rendered_to_page_images():
    result = extract("pdf", scanned_pdf(3), 10)
    assert result.method == "vision" and result.page_count == 3 and len(result.images) == 3
    assert all(max(decoded(i).size) <= 1600 for i in result.images)


def test_scanned_pdf_without_ai_keeps_the_old_answer():
    with pytest.raises(UploadRejected) as info:
        extract("pdf", scanned_pdf(), 0)
    assert info.value.code == "no_text"


def test_long_scans_are_refused_before_rendering():
    with pytest.raises(UploadRejected) as info:
        extract("pdf", scanned_pdf(4), 3)
    assert info.value.code == "scan_too_long" and "3 pages" in info.value.message


def test_text_pdfs_never_go_to_ai():
    result = extract("pdf", samples.pdf("Clinic opening hours are 8am to 5pm on weekdays."), 10)
    assert result.method == "text" and result.images == () and "8am" in result.text


def test_active_content_is_still_refused_for_scans():
    with pytest.raises(UploadRejected) as info:
        extract("pdf", samples.pdf_with_javascript(), 10)
    assert info.value.code == "active_content"


# ----- gateway payload ---------------------------------------------------------------------------
def test_gateway_sends_images_as_data_urls_with_zdr_and_price_cap():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        return httpx.Response(200, json={"model": "google/gemma-4-26b-a4b-it",
                                         "choices": [{"message": {"content": "Eye exam 25,000"}}],
                                         "usage": {"prompt_tokens": 900, "completion_tokens": 8,
                                                   "cost": 0.0001}})

    gateway = OpenRouterGateway("k", "https://openrouter.ai/api/v1", 5, CEILING,
                                transport=httpx.MockTransport(handler))
    reader = VisionReader(gateway, ("google/gemma-4-26b-a4b-it", "openai/gpt-6-luna"), CEILING)
    result = reader.read(["QUJD"])
    assert result.text == "Eye exam 25,000" and result.error is None
    assert seen["models"] == ["google/gemma-4-26b-a4b-it", "openai/gpt-6-luna"]
    assert seen["provider"]["zdr"] is True and seen["provider"]["data_collection"] == "deny"
    assert seen["provider"]["max_price"] == {"prompt": 0.5, "completion": 1.0}
    assert seen["temperature"] == 0 and seen["max_tokens"] == 1500
    user = seen["messages"][1]["content"]
    assert user[1] == {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,QUJD"}}
    assert seen["messages"][0]["role"] == "system" and isinstance(seen["messages"][0]["content"], str)
    assert result.usage[0].tier == "vision" and result.usage[0].cost_usd == Decimal("0.0001")


# ----- vision reader -----------------------------------------------------------------------------
def test_pages_are_read_in_order_and_cleaned():
    replies = {"cGFnZTE=": "```\nPrices\nEye exam | 25,000\n```", "cGFnZTI=": NO_TEXT,
               "cGFnZTM=": "Contact lenses\x00 | 40,000"}
    fake = FakeGateway(lambda r: replies[r.messages[1].images[0]])
    result = VisionReader(fake, ("fake/v",), CEILING).read(list(replies))
    assert result.text == "Prices\nEye exam | 25,000\n\nContact lenses | 40,000"
    assert len(result.usage) == 3 and len(fake.requests) == 3


def test_nothing_readable_gives_empty_text():
    result = VisionReader(FakeGateway(lambda r: f" {NO_TEXT} "), ("fake/v",), CEILING).read(["QQ=="])
    assert result.text == "" and result.error is None


def test_a_failed_page_fails_the_file_but_keeps_billed_usage():
    worst = ModelResult("", "fake/v", 3000, 1500, Decimal("0.003"))

    def script(request):
        if request.messages[1].images[0] == "YmFk":
            raise ModelError("timeout", worst)
        return "fine"

    result = VisionReader(FakeGateway(script), ("fake/v",), CEILING).read(["b2s=", "YmFk"])
    assert result.error == "timeout" and result.text == ""
    assert sorted(u.cost_usd for u in result.usage) == [FakeGateway.COST, Decimal("0.003")]


def test_worst_case_covers_every_page():
    reader = VisionReader(FakeGateway(lambda r: ""), ("fake/v",), CEILING, max_output_tokens=1500)
    one = reader.worst_case(1)
    assert one > CEILING.cost(3000, 1500) - Decimal("0.0001")  # image estimate + full output
    assert reader.worst_case(10) == one * 10


def test_clean_transcription_caps_length():
    assert len(clean_transcription("a" * 400_000)) == 300_000


# ----- settings ------------------------------------------------------------------------------------
def test_vision_is_off_by_default_and_needs_a_key():
    from pydantic import ValidationError

    from app.config import Settings
    from app.services.ai.factory import build_vision_reader

    assert build_vision_reader(Settings(_env_file=None)) is None
    with pytest.raises(ValidationError):
        Settings(_env_file=None, ai_vision_enabled=True)
    on = Settings(_env_file=None, ai_vision_enabled=True, openrouter_api_key="k")
    reader = build_vision_reader(on)
    assert reader is not None and reader.models[0] == "google/gemma-4-26b-a4b-it"


def test_plain_http_model_url_only_for_a_local_fake_in_development():
    from pydantic import ValidationError

    from app.config import Settings

    Settings(_env_file=None, ai_vision_enabled=True, openrouter_api_key="k",
             openrouter_base_url="http://127.0.0.1:4182")
    with pytest.raises(ValidationError):
        Settings(_env_file=None, ai_vision_enabled=True, openrouter_api_key="k",
                 openrouter_base_url="http://openrouter.example.com/api/v1")
    with pytest.raises(ValidationError):
        Settings(_env_file=None, app_env="staging", ai_vision_enabled=True, openrouter_api_key="k",
                 openrouter_base_url="http://127.0.0.1:4182")


@pytest.mark.parametrize("models", ["~google/gemma-latest", "a/b,c/d,e/f,g/h", ""])
def test_vision_models_must_be_pinned(models):
    from pydantic import ValidationError

    from app.config import Settings

    with pytest.raises(ValidationError):
        Settings(_env_file=None, ai_vision_models=models)
