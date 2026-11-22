"""Phase 3g: photos and scanned PDFs uploaded by clinic staff, read by a (fake) vision model,
through the real API, RLS, plan gates, budgets and usage ledger. No real model calls."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.services.ai.answerer import Budget
from app.services.ai.gateway import FakeGateway, ModelError, ModelResult, PriceCeiling
from app.services.ai.vision import VisionReader
from tests import samples
from tests.test_vision import picture, scanned_pdf

pytestmark = pytest.mark.integration

CEILING = PriceCeiling(Decimal("0.50"), Decimal("1.00"))
OPEN_BUDGET = Budget(Decimal("0.20"), Decimal("0.50"), Decimal("2.00"))
REASON = "vision test"
PRICE_LIST = "Price list\nComprehensive eye exam | 25,000\nContact lens fitting | 15,000"


def use_vision(app_state, script=lambda r: PRICE_LIST, budget=OPEN_BUDGET) -> FakeGateway:
    fake = FakeGateway(script)
    app_state("vision_reader", VisionReader(fake, ("fake/vision",), CEILING))
    app_state("ai_budget", budget)
    return fake


@pytest.fixture(autouse=True)
def clean_overrides(admin_db, world):
    yield
    admin_db.execute("delete from public.tenant_overrides where tenant_id = any(%s) and reason = %s",
                     ([world.tenant_a, world.tenant_b], REASON))


def upload(client, user, tenant, name="prices.jpg", data=None, mime="image/jpeg", title="Price list"):
    return client.post(f"/api/v1/tenants/{tenant}/knowledge", headers=user.auth,
                       data={"title": title},
                       files={"file": (name, data if data is not None else picture(fmt="JPEG"), mime)})


def documents(admin_db, tenant) -> int:
    return admin_db.execute("select count(*) from public.knowledge_documents where tenant_id = %s",
                            (tenant,)).fetchone()[0]


def vision_usage(admin_db, tenant) -> list[tuple]:
    return admin_db.execute(
        "select feature, tier, conversation_id, provider, cost_usd from public.usage_events "
        "where tenant_id = %s and feature = 'document' order by id", (tenant,)).fetchall()


def ai_meter(admin_db, tenant) -> float:
    row = admin_db.execute("select quantity from app_private.usage_counters where tenant_id = %s "
                           "and metric = 'ai_usd' and period_month = app_private.current_period()",
                           (tenant,)).fetchone()
    return float(row[0]) if row else 0.0


def override(admin_db, tenant, **values):
    kind = "feature" if "feature_enabled" in values else "limit"
    admin_db.execute(
        "insert into public.tenant_overrides (tenant_id, kind, key, feature_enabled, limit_value, reason) "
        "values (%s, %s, %s, %s, %s, %s) on conflict (tenant_id, kind, key) do update set "
        "feature_enabled = excluded.feature_enabled, limit_value = excluded.limit_value",
        (tenant, kind, values["key"], values.get("feature_enabled"), values.get("limit_value"), REASON))


# ----- happy paths -----------------------------------------------------------------------------
def test_photo_is_read_by_ai_and_waits_for_review(client, world, admin_db, app_state):
    fake = use_vision(app_state)
    usage_before, meter_before = len(vision_usage(admin_db, world.tenant_a)), ai_meter(admin_db, world.tenant_a)
    response = upload(client, world.a_owner, world.tenant_a)
    assert response.status_code == 201, response.text
    doc = response.json()
    version = doc["versions"][0]
    assert (doc["state"], version["status"]) == ("awaiting_review", "extracted")
    assert (version["detected_type"], version["extraction_method"]) == ("image", "vision")
    detail = client.get(f"/api/v1/tenants/{world.tenant_a}/knowledge/{doc['id']}/versions/{version['id']}",
                        headers=world.a_owner.auth).json()
    assert detail["extracted_text"] == PRICE_LIST
    # One model call with exactly one image, recorded as document usage and metered.
    assert len(fake.requests) == 1 and len(fake.requests[0].messages[1].images) == 1
    rows = vision_usage(admin_db, world.tenant_a)
    assert len(rows) == usage_before + 1
    assert rows[-1][:4] == ("document", "vision", None, "fake")
    assert ai_meter(admin_db, world.tenant_a) > meter_before
    audit = admin_db.execute(
        "select metadata->>'extraction_method' from public.audit_events where action = 'knowledge.uploaded' "
        "and target_id = %s", (doc["id"],)).fetchone()[0]
    assert audit == "vision"


def test_scanned_pdf_pages_are_each_read(client, world, app_state):
    pages = iter(["Opening hours", "Mon-Fri 8am - 5pm"])
    fake = use_vision(app_state, lambda r: next(pages))
    response = upload(client, world.a_owner, world.tenant_a, "scan.pdf", scanned_pdf(2), "application/pdf",
                      title="Scanned opening hours")
    assert response.status_code == 201, response.text
    version = response.json()["versions"][0]
    assert (version["detected_type"], version["extraction_method"], version["page_count"]) == ("pdf", "vision", 2)
    assert len(fake.requests) == 2


def test_text_documents_never_call_the_model(client, world, app_state):
    fake = use_vision(app_state)
    response = upload(client, world.a_owner, world.tenant_a, "hours.pdf",
                      samples.pdf("Clinic opening hours are 8am to 5pm on weekdays."), "application/pdf",
                      title="Hours text")
    assert response.status_code == 201
    assert response.json()["versions"][0]["extraction_method"] == "text"
    assert fake.requests == []


def test_new_version_can_be_a_photo(client, world, app_state):
    use_vision(app_state)
    doc = upload(client, world.a_owner, world.tenant_a, title="Flyer").json()
    response = client.post(f"/api/v1/tenants/{world.tenant_a}/knowledge/{doc['id']}/versions",
                           headers=world.a_owner.auth,
                           files={"file": ("flyer.png", picture(size=(900, 600)), "image/png")})
    assert response.status_code == 201, response.text
    assert response.json()["versions"][0]["extraction_method"] == "vision"


# ----- refusals: nothing stored, no model call -------------------------------------------------
def test_without_ai_photos_are_refused_and_scans_say_no_text(client, world, admin_db, app_state):
    app_state("vision_reader", None)
    before = documents(admin_db, world.tenant_a)
    photo = upload(client, world.a_owner, world.tenant_a)
    assert photo.status_code == 422 and photo.json()["error"]["code"] == "upload_vision_unavailable"
    scan = upload(client, world.a_owner, world.tenant_a, "scan.pdf", scanned_pdf(), "application/pdf")
    assert scan.status_code == 422 and scan.json()["error"]["code"] == "upload_no_text"
    assert documents(admin_db, world.tenant_a) == before


def test_feature_switched_off_refuses_photos(client, world, admin_db, app_state):
    fake = use_vision(app_state)
    override(admin_db, world.tenant_a, key="document_reading", feature_enabled=False)
    photo = upload(client, world.a_owner, world.tenant_a)
    assert photo.status_code == 403 and photo.json()["error"]["code"] == "feature_not_in_plan"
    scan = upload(client, world.a_owner, world.tenant_a, "scan.pdf", scanned_pdf(), "application/pdf")
    assert scan.status_code == 422 and scan.json()["error"]["code"] == "upload_no_text"
    assert fake.requests == []


def test_daily_budget_is_checked_before_any_call(client, world, admin_db, app_state):
    fake = use_vision(app_state, budget=Budget(Decimal("0.001"), Decimal("0.50"), Decimal("2.00")))
    before = documents(admin_db, world.tenant_a)
    response = upload(client, world.a_owner, world.tenant_a, "scan.pdf", scanned_pdf(3), "application/pdf")
    assert response.status_code == 409 and response.json()["error"]["code"] == "ai_budget_reached"
    assert fake.requests == [] and documents(admin_db, world.tenant_a) == before


def test_monthly_plan_allowance_is_checked_before_any_call(client, world, admin_db, app_state):
    fake = use_vision(app_state)
    override(admin_db, world.tenant_a, key="ai_usd_month", limit_value=0)
    response = upload(client, world.a_owner, world.tenant_a)
    assert response.status_code == 409 and response.json()["error"]["code"] == "quota_reached"
    assert fake.requests == []


def test_model_failure_stores_nothing_but_records_billed_usage(client, world, admin_db, app_state):
    worst = ModelResult("", "fake/vision", 3000, 1500, Decimal("0.003"))

    def fail(request):
        raise ModelError("timeout", worst)

    use_vision(app_state, fail)
    before_docs, before_usage = documents(admin_db, world.tenant_a), len(vision_usage(admin_db, world.tenant_a))
    response = upload(client, world.a_owner, world.tenant_a)
    assert response.status_code == 422 and response.json()["error"]["code"] == "upload_vision_failed"
    assert documents(admin_db, world.tenant_a) == before_docs
    usage = vision_usage(admin_db, world.tenant_a)
    assert len(usage) == before_usage + 1 and usage[-1][4] == Decimal("0.003")


def test_blank_photo_is_rejected_as_no_text(client, world, app_state):
    use_vision(app_state, lambda r: "NO_TEXT")
    response = upload(client, world.a_owner, world.tenant_a)
    assert response.status_code == 422 and response.json()["error"]["code"] == "upload_no_text"


def test_only_owners_and_admins_of_that_clinic(client, world, app_state):
    fake = use_vision(app_state)
    assert upload(client, world.a_receptionist, world.tenant_a).status_code == 403
    assert upload(client, world.b_owner, world.tenant_a).status_code in (403, 404)
    assert fake.requests == []
