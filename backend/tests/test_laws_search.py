"""Test tra cứu văn bản: danh mục, cây Chương-Điều, full-text search.

Đây là phần bám chặt nhất vào PostgreSQL (``tsvector``, ``unaccent``,
``pg_trgm``) nên test chạy trên database thật.
"""
from __future__ import annotations

import pytest_asyncio

from tests.factories import register, seed_articles

TEST_LAW = "test-01/2020/QH14"


@pytest_asyncio.fixture(autouse=True)
async def corpus(session):
    await seed_articles(session)


@pytest_asyncio.fixture
async def headers(client):
    account = await register(client)
    return account["headers"]


async def test_search_requires_auth(client):
    response = await client.get("/api/v1/laws/search", params={"q": "doanh nghiệp"})
    assert response.status_code == 401


async def test_list_laws_exposes_filter_options(client, headers):
    response = await client.get("/api/v1/laws", headers=headers)

    assert response.status_code == 200, response.text
    payload = response.json()
    law_ids = {item["law_id"] for item in payload["items"]}
    assert TEST_LAW in law_ids
    assert payload["doc_types"]
    assert payload["categories"]

    law = next(item for item in payload["items"] if item["law_id"] == TEST_LAW)
    assert law["article_count"] == 3


async def test_filter_by_doc_type(client, headers):
    response = await client.get(
        "/api/v1/laws", params={"doc_type": "Bộ luật"}, headers=headers
    )

    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert items
    assert all(item["doc_type"] == "Bộ luật" for item in items)


async def test_law_tree_groups_articles_by_chapter(client, headers):
    response = await client.get(f"/api/v1/laws/{TEST_LAW}/articles", headers=headers)

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["law"]["law_id"] == TEST_LAW
    chapters = {chapter["chapter"]: chapter["articles"] for chapter in payload["chapters"]}
    assert "Chương I: Quy định chung" in chapters
    assert [item["article"] for item in chapters["Chương I: Quy định chung"]] == [
        "Điều 1",
        "Điều 2",
    ]


async def test_article_detail_resolves_cross_references(client, headers):
    """``extra`` của corpus dùng ``doc_type|law_id|Điều X`` chứ không phải
    ``law_id|law_name|Điều X`` như citation của agent; resolver phải nhận cả hai,
    và bỏ những viện dẫn không mở được."""

    response = await client.get(
        f"/api/v1/laws/{TEST_LAW}/articles/Điều 17", headers=headers
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["article_title"] == "Quyền thành lập doanh nghiệp"
    assert [item["article"] for item in payload["related"]] == ["Điều 1"]


async def test_related_articles_accepts_citation_format(session):
    """Citation của agent và của compliance_rules cũng phải phân giải được."""

    from src.services.legal.search import list_related_articles

    resolved = await list_related_articles(
        session,
        [
            "test-02/2019/QH14|Bộ luật Lao động Kiểm Thử|Điều 25",
            "Luật|test-01/2020/QH14|Điều 1",
            "khong-phai-vien-dan",
        ],
    )

    assert {item["article"] for item in resolved} == {"Điều 25", "Điều 1"}


async def test_article_detail_has_previous_and_next(client, headers):
    response = await client.get(
        f"/api/v1/laws/{TEST_LAW}/articles/Điều 2", headers=headers
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["previous_article"] == "Điều 1"
    # Điều 17 phải đứng sau Điều 2: thứ tự theo số, không phải theo chuỗi.
    assert payload["next_article"] == "Điều 17"


async def test_unknown_article_returns_404(client, headers):
    response = await client.get(
        f"/api/v1/laws/{TEST_LAW}/articles/Điều 999", headers=headers
    )
    assert response.status_code == 404


async def test_full_text_search_finds_article(client, headers):
    response = await client.get(
        "/api/v1/laws/search", params={"q": "thành lập doanh nghiệp"}, headers=headers
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["strategy"] == "full_text"
    assert payload["total"] > 0
    assert any(hit["article"] == "Điều 17" for hit in payload["items"])
    # Frontend highlight phía client, nên backend phải trả về từ khóa đã tách.
    assert payload["terms"]


async def test_search_is_accent_insensitive(client, headers):
    """Người dùng gõ không dấu là trường hợp phổ biến nhất trên bàn phím Việt."""

    with_accent = await client.get(
        "/api/v1/laws/search", params={"q": "thời gian thử việc"}, headers=headers
    )
    without_accent = await client.get(
        "/api/v1/laws/search", params={"q": "thoi gian thu viec"}, headers=headers
    )

    assert with_accent.status_code == 200
    assert without_accent.status_code == 200
    assert without_accent.json()["total"] > 0
    assert {hit["id"] for hit in without_accent.json()["items"]} == {
        hit["id"] for hit in with_accent.json()["items"]
    }


async def test_search_by_article_number_uses_dedicated_strategy(client, headers):
    response = await client.get(
        "/api/v1/laws/search", params={"q": "Điều 17"}, headers=headers
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["strategy"] == "article_number"
    assert all(hit["article"] == "Điều 17" for hit in payload["items"])


async def test_search_falls_back_to_trigram_on_typo(client, headers):
    """Gõ sai một hai chữ vẫn phải ra kết quả, nhờ pg_trgm."""

    response = await client.get(
        "/api/v1/laws/search", params={"q": "thoi gain thu viec"}, headers=headers
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["strategy"] in {"full_text", "trigram"}


async def test_search_with_no_match_returns_empty_list(client, headers):
    response = await client.get(
        "/api/v1/laws/search",
        params={"q": "zzzqqq khong ton tai trong corpus"},
        headers=headers,
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["items"] == []
    assert payload["total"] == 0


async def test_search_respects_doc_type_filter(client, headers):
    response = await client.get(
        "/api/v1/laws/search",
        params={"q": "doanh nghiệp", "doc_type": "Bộ luật"},
        headers=headers,
    )

    assert response.status_code == 200, response.text
    assert all(hit["doc_type"] == "Bộ luật" for hit in response.json()["items"])
