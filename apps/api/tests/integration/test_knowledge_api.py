"""Phase 2c knowledge documents through the real API, real RLS and real local Storage.

Covers: upload -> extract -> review -> publish -> new version -> republish; rejection of
dangerous files (never stored); roles; cross-tenant denial; archive; duplicate detection;
size limit; storage failure rollback; originals unreachable from browsers.
"""

from __future__ import annotations

import httpx
import pytest

from app.services.storage import StorageError
from tests import samples

pytestmark = pytest.mark.integration

PDF = "application/pdf"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def url(tenant: str, path: str = "") -> str:
    return f"/api/v1/tenants/{tenant}/knowledge{path}"


def upload(client, user, tenant, name="hours.pdf", data=None, title="Opening hours", mime=PDF):
    return client.post(
        url(tenant),
        headers=user.auth,
        data={"title": title},
        files={"file": (name, data if data is not None else samples.pdf(), mime)},
    )


def uploaded(client, user, tenant, **kwargs) -> dict:
    response = upload(client, user, tenant, **kwargs)
    assert response.status_code == 201, response.text
    return response.json()


def object_exists(admin_db, path: str) -> bool:
    return (
        admin_db.execute(
            "select count(*) from storage.objects where bucket_id = 'knowledge-originals' "
            "and name = %s",
            (path,),
        ).fetchone()[0]
        == 1
    )


def storage_path(admin_db, version_id: str) -> str:
    return admin_db.execute(
        "select storage_path from public.knowledge_document_versions where id = %s", (version_id,)
    ).fetchone()[0]


def test_upload_review_publish_and_version_cycle(client, world, admin_db):
    doc = uploaded(
        client, world.a_owner, world.tenant_a, data=samples.pdf("Walk-ins welcome 8am to 5pm")
    )
    assert doc["state"] == "awaiting_review"
    v1 = doc["versions"][0]
    assert (v1["version_no"], v1["status"], v1["detected_type"], v1["is_published"]) == (
        1,
        "extracted",
        "pdf",
        False,
    )
    assert object_exists(admin_db, storage_path(admin_db, v1["id"]))

    detail = client.get(
        url(world.tenant_a, f"/{doc['id']}/versions/{v1['id']}"), headers=world.a_receptionist.auth
    )
    assert detail.status_code == 200
    assert "Walk-ins welcome 8am to 5pm" in detail.json()["extracted_text"]

    approve = client.post(
        url(world.tenant_a, f"/{doc['id']}/versions/{v1['id']}/approve"),
        headers=world.a_owner.auth,
        json={"note": "Checked against website"},
    )
    assert approve.status_code == 200, approve.text
    assert approve.json()["state"] == "published"
    assert approve.json()["published_version"]["version_no"] == 1

    v2_response = client.post(
        url(world.tenant_a, f"/{doc['id']}/versions"),
        headers=world.a_admin.auth,
        files={"file": ("hours.docx", samples.docx("Now open Saturdays 9am to 1pm"), DOCX)},
    )
    assert v2_response.status_code == 201, v2_response.text
    pending = v2_response.json()
    assert pending["state"] == "changes_pending"
    assert pending["published_version"]["version_no"] == 1  # v1 stays live during review
    v2 = pending["latest_version"]
    assert (v2["version_no"], v2["detected_type"]) == (2, "docx")

    republish = client.post(
        url(world.tenant_a, f"/{doc['id']}/versions/{v2['id']}/approve"),
        headers=world.a_admin.auth,
        json={},
    )
    assert republish.json()["published_version"]["version_no"] == 2
    assert republish.json()["state"] == "published"

    actions = [
        r[0]
        for r in admin_db.execute(
            "select action from public.audit_events where target_id = %s order by id", (doc["id"],)
        ).fetchall()
    ]
    assert actions == [
        "knowledge.uploaded",
        "knowledge.published",
        "knowledge.version_uploaded",
        "knowledge.published",
    ]


def test_reject_and_invalid_transitions(client, world):
    doc = uploaded(
        client,
        world.a_owner,
        world.tenant_a,
        name="faq.md",
        data=b"# FAQ\n\nWe accept most HMO plans.",
        mime="text/markdown",
    )
    version_id = doc["versions"][0]["id"]
    base = url(world.tenant_a, f"/{doc['id']}/versions/{version_id}")
    rejected = client.post(
        f"{base}/reject", headers=world.a_owner.auth, json={"note": "Outdated list"}
    )
    assert rejected.json()["versions"][0]["status"] == "rejected"
    assert rejected.json()["state"] == "unpublished"
    again = client.post(f"{base}/approve", headers=world.a_owner.auth, json={})
    assert again.status_code == 409


@pytest.mark.parametrize(
    ("name", "build", "mime", "code"),
    [
        ("hours.pdf", samples.pdf_with_javascript, PDF, "upload_active_content"),
        ("hours.pdf", samples.pdf_with_attachment, PDF, "upload_embedded_files"),
        ("hours.pdf", samples.pdf_encrypted, PDF, "upload_encrypted"),
        ("faq.docx", samples.docx_with_macros, DOCX, "upload_macros"),
        ("faq.docx", samples.docx_zip_bomb, DOCX, "upload_too_complex"),
        (
            "tool.exe",
            lambda: b"MZ\x90\x00binary",
            "application/octet-stream",
            "upload_unsupported_type",
        ),
        ("hours.pdf", samples.docx, PDF, "upload_type_mismatch"),  # MIME/extension lie
        ("scan.pdf", samples.pdf_blank, PDF, "upload_no_text"),
    ],
    ids=[
        "pdf-js",
        "pdf-attachment",
        "pdf-encrypted",
        "docx-macros",
        "zip-bomb",
        "exe",
        "docx-named-pdf",
        "scanned-pdf",
    ],
)
def test_dangerous_or_unusable_files_are_rejected_and_never_stored(
    client, world, admin_db, name, build, mime, code
):
    before_docs = admin_db.execute("select count(*) from public.knowledge_documents").fetchone()[0]
    before_objects = admin_db.execute(
        "select count(*) from storage.objects where bucket_id = 'knowledge-originals'"
    ).fetchone()[0]
    response = upload(client, world.a_owner, world.tenant_a, name=name, data=build(), mime=mime)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == code
    assert (
        admin_db.execute("select count(*) from public.knowledge_documents").fetchone()[0]
        == before_docs
    )
    assert (
        admin_db.execute(
            "select count(*) from storage.objects where bucket_id = 'knowledge-originals'"
        ).fetchone()[0]
        == before_objects
    )
    reason = code.removeprefix("upload_")
    logged = admin_db.execute(
        "select count(*) from public.audit_events where action = 'knowledge.upload_rejected' "
        "and tenant_id = %s and metadata->>'reason' = %s",
        (world.tenant_a, reason),
    ).fetchone()[0]
    assert logged >= 1


def test_receptionist_can_read_but_not_upload_or_review(client, world):
    doc = uploaded(client, world.a_owner, world.tenant_a)
    version_id = doc["versions"][0]["id"]
    headers = world.a_receptionist.auth
    assert client.get(url(world.tenant_a), headers=headers).status_code == 200
    denied = [
        upload(client, world.a_receptionist, world.tenant_a),
        client.post(
            url(world.tenant_a, f"/{doc['id']}/versions"),
            headers=headers,
            files={"file": ("v2.txt", b"new text", "text/plain")},
        ),
        client.post(
            url(world.tenant_a, f"/{doc['id']}/versions/{version_id}/approve"),
            headers=headers,
            json={},
        ),
        client.post(
            url(world.tenant_a, f"/{doc['id']}/versions/{version_id}/reject"),
            headers=headers,
            json={},
        ),
        client.post(url(world.tenant_a, f"/{doc['id']}/archive"), headers=headers),
        client.patch(
            url(world.tenant_a, f"/{doc['id']}"), headers=headers, json={"title": "Renamed"}
        ),
    ]
    assert [r.status_code for r in denied] == [403] * 6


def test_other_tenant_cannot_reach_documents(client, world):
    doc = uploaded(client, world.a_owner, world.tenant_a)
    version_id = doc["versions"][0]["id"]
    attacker = world.b_owner.auth
    for response in (
        client.get(url(world.tenant_a), headers=attacker),
        client.get(url(world.tenant_a, f"/{doc['id']}"), headers=attacker),
        client.get(url(world.tenant_a, f"/{doc['id']}/versions/{version_id}"), headers=attacker),
        client.post(
            url(world.tenant_a, f"/{doc['id']}/versions/{version_id}/approve"),
            headers=attacker,
            json={},
        ),
        upload(client, world.b_owner, world.tenant_a),
        # Own tenant in the path, Tenant A's ids (guessed UUIDs):
        client.get(url(world.tenant_b, f"/{doc['id']}"), headers=attacker),
        client.get(url(world.tenant_b, f"/{doc['id']}/versions/{version_id}"), headers=attacker),
        client.post(
            url(world.tenant_b, f"/{doc['id']}/versions/{version_id}/approve"),
            headers=attacker,
            json={},
        ),
        client.post(
            url(world.tenant_b, f"/{doc['id']}/versions"),
            headers=attacker,
            files={"file": ("x.txt", b"injected text", "text/plain")},
        ),
        client.get(url(world.tenant_a), headers=world.outsider.auth),
    ):
        assert response.status_code == 404
    still = client.get(url(world.tenant_a, f"/{doc['id']}"), headers=world.a_owner.auth).json()
    assert len(still["versions"]) == 1 and still["state"] == "awaiting_review"


def test_archive_unpublishes_and_blocks_new_versions(client, world):
    doc = uploaded(client, world.a_owner, world.tenant_a)
    version_id = doc["versions"][0]["id"]
    client.post(
        url(world.tenant_a, f"/{doc['id']}/versions/{version_id}/approve"),
        headers=world.a_owner.auth,
        json={},
    )
    archived = client.post(url(world.tenant_a, f"/{doc['id']}/archive"), headers=world.a_owner.auth)
    assert (archived.json()["state"], archived.json()["published_version"]) == ("archived", None)
    blocked = client.post(
        url(world.tenant_a, f"/{doc['id']}/versions"),
        headers=world.a_owner.auth,
        files={"file": ("v2.txt", b"new text", "text/plain")},
    )
    assert blocked.status_code == 409
    restored = client.post(url(world.tenant_a, f"/{doc['id']}/restore"), headers=world.a_owner.auth)
    assert restored.json()["state"] == "unpublished"  # restoring never republishes


def test_duplicate_version_is_refused(client, world):
    data = samples.docx("Price list 2026")
    doc = uploaded(client, world.a_owner, world.tenant_a, name="prices.docx", data=data, mime=DOCX)
    again = client.post(
        url(world.tenant_a, f"/{doc['id']}/versions"),
        headers=world.a_owner.auth,
        files={"file": ("prices.docx", data, DOCX)},
    )
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "duplicate_version"


def test_oversized_request_is_refused_before_parsing(client, world):
    big = b"a" * (11 * 1024 * 1024)
    response = upload(
        client, world.a_owner, world.tenant_a, name="big.txt", data=big, mime="text/plain"
    )
    assert response.status_code == 413


def test_storage_failure_rolls_back_the_upload(client, world, admin_db, app_state):
    class BrokenStore:
        def put(self, path, data):
            raise StorageError("down")

    app_state("object_store", BrokenStore())
    before = admin_db.execute("select count(*) from public.knowledge_documents").fetchone()[0]
    response = upload(client, world.a_owner, world.tenant_a, title="Will not persist")
    assert response.status_code == 503
    assert (
        admin_db.execute("select count(*) from public.knowledge_documents").fetchone()[0] == before
    )


def test_originals_cannot_be_downloaded_from_a_browser(client, world, stack, admin_db):
    doc = uploaded(client, world.a_owner, world.tenant_a)
    path = storage_path(admin_db, doc["versions"][0]["id"])
    base = f"{stack['API_URL']}/storage/v1/object"
    as_owner = {
        "apikey": stack["PUBLISHABLE_KEY"],
        "Authorization": f"Bearer {world.a_owner.token}",
    }
    as_anon = {"apikey": stack["PUBLISHABLE_KEY"]}
    for attempt in (
        httpx.get(f"{base}/authenticated/knowledge-originals/{path}", headers=as_owner, timeout=10),
        httpx.get(f"{base}/public/knowledge-originals/{path}", timeout=10),
        httpx.get(f"{base}/knowledge-originals/{path}", headers=as_anon, timeout=10),
        httpx.post(
            f"{base}/list/knowledge-originals",
            headers=as_owner,
            json={"prefix": world.tenant_a},
            timeout=10,
        ),
    ):
        assert attempt.status_code != 200 or attempt.json() == [], attempt.text
    sign = httpx.post(
        f"{base}/sign/knowledge-originals/{path}",
        headers=as_owner,
        json={"expiresIn": 60},
        timeout=10,
    )
    assert sign.status_code != 200
    overwrite = httpx.post(
        f"{base}/knowledge-originals/{path}", headers=as_owner, content=b"tampered", timeout=10
    )
    assert overwrite.status_code not in (200, 201)
