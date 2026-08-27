"""Test tải hợp đồng: trích text, cách ly theo doanh nghiệp."""
from __future__ import annotations

from tests.factories import register

SAMPLE_CONTRACT = (
    "HỢP ĐỒNG LAO ĐỘNG\n\n"
    "Điều 1. Thời gian thử việc\n"
    "Bên B thử việc 90 ngày đối với vị trí nhân viên kinh doanh.\n\n"
    "Điều 2. Thời giờ làm việc\n"
    "Bên B làm việc 10 giờ/ngày, 6 ngày/tuần.\n"
)


async def test_upload_requires_organization(client):
    account = await register(client)
    response = await client.post(
        "/api/v1/documents",
        files={"file": ("hop-dong.txt", SAMPLE_CONTRACT.encode("utf-8"), "text/plain")},
        headers=account["headers"],
    )
    assert response.status_code == 400, response.text


async def test_upload_txt_extracts_text(client):
    account = await register(client, with_organization=True)
    response = await client.post(
        "/api/v1/documents",
        files={"file": ("hop-dong.txt", SAMPLE_CONTRACT.encode("utf-8"), "text/plain")},
        headers=account["headers"],
    )

    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["filename"] == "hop-dong.txt"
    assert payload["status"] == "ready"
    assert payload["text_length"] >= 100


async def test_list_and_get_document(client):
    account = await register(client, with_organization=True)
    created = await client.post(
        "/api/v1/documents",
        files={"file": ("hd.txt", SAMPLE_CONTRACT.encode("utf-8"), "text/plain")},
        headers=account["headers"],
    )
    document_id = created.json()["id"]

    listed = await client.get("/api/v1/documents", headers=account["headers"])
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert listed.json()["items"][0]["id"] == document_id

    detail = await client.get(f"/api/v1/documents/{document_id}", headers=account["headers"])
    assert detail.status_code == 200
    assert detail.json()["filename"] == "hd.txt"


async def test_document_isolated_between_orgs(client):
    first = await register(client, with_organization=True)
    second = await register(client, with_organization=True)
    created = await client.post(
        "/api/v1/documents",
        files={"file": ("bi-mat.txt", SAMPLE_CONTRACT.encode("utf-8"), "text/plain")},
        headers=first["headers"],
    )
    document_id = created.json()["id"]

    other = await client.get(f"/api/v1/documents/{document_id}", headers=second["headers"])
    assert other.status_code == 404


async def test_delete_document(client):
    account = await register(client, with_organization=True)
    created = await client.post(
        "/api/v1/documents",
        files={"file": ("xoa.txt", SAMPLE_CONTRACT.encode("utf-8"), "text/plain")},
        headers=account["headers"],
    )
    document_id = created.json()["id"]

    deleted = await client.delete(
        f"/api/v1/documents/{document_id}", headers=account["headers"]
    )
    assert deleted.status_code == 204

    missing = await client.get(f"/api/v1/documents/{document_id}", headers=account["headers"])
    assert missing.status_code == 404
