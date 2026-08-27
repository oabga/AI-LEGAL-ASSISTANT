"""Helper tạo dữ liệu test: tài khoản và một vài Điều luật mẫu."""
from __future__ import annotations

import uuid
from typing import Any

import httpx

PASSWORD = "TestPassword#2026"


def unique_email(prefix: str = "user") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}@example.com"


def unique_tax_code() -> str:
    """organizations.tax_code là unique nên mỗi lần đăng ký phải khác nhau."""

    return f"01{uuid.uuid4().int % 10**8:08d}"


async def register(
    client: httpx.AsyncClient,
    *,
    email: str | None = None,
    role: str = "owner",
    with_organization: bool = False,
    employee_count: int = 12,
    vat_period: str = "quarterly",
) -> dict[str, Any]:
    """Đăng ký tài khoản, trả về payload kèm ``headers`` đã có Bearer token."""

    payload: dict[str, Any] = {
        "email": email or unique_email(role),
        "password": PASSWORD,
        "full_name": "Nguyễn Văn Test",
        "role": role,
    }
    if with_organization:
        payload["organization"] = {
            "name": "Công ty TNHH Kiểm Thử",
            "tax_code": unique_tax_code(),
            "business_type": "Công ty TNHH một thành viên",
            "employee_count": employee_count,
            "vat_period": vat_period,
        }

    response = await client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 201, response.text
    data = response.json()
    return {
        **data,
        "email": payload["email"],
        "password": PASSWORD,
        "headers": {"Authorization": f"Bearer {data['tokens']['access_token']}"},
    }


# Điều luật mẫu, đủ để kiểm chứng cây Chương-Điều, viện dẫn chéo và full-text.
# ``id`` là primary key không autoincrement, phải khai báo tường minh; dải
# 9_000_00x tránh đụng id thật của corpus.
SAMPLE_ARTICLES: list[dict[str, Any]] = [
    {
        "id": 9_000_001,
        "law_id": "test-01/2020/QH14",
        "law_name": "Luật Doanh nghiệp Kiểm Thử",
        "doc_type": "Luật",
        "chapter": "Chương I: Quy định chung",
        "article": "Điều 1",
        "article_title": "Phạm vi điều chỉnh",
        "content": "Luật này quy định về việc thành lập doanh nghiệp và tổ chức quản lý doanh nghiệp.",
        # Định dạng viện dẫn của corpus thật: doc_type|law_id|Điều X.
        "extra": ["Luật|test-01/2020/QH14|Điều 2"],
    },
    {
        "id": 9_000_002,
        "law_id": "test-01/2020/QH14",
        "law_name": "Luật Doanh nghiệp Kiểm Thử",
        "doc_type": "Luật",
        "chapter": "Chương I: Quy định chung",
        "article": "Điều 2",
        "article_title": "Đối tượng áp dụng",
        "content": "Luật này áp dụng với doanh nghiệp nhỏ và vừa, hộ kinh doanh chuyển đổi.",
        "extra": [],
    },
    {
        "id": 9_000_003,
        "law_id": "test-01/2020/QH14",
        "law_name": "Luật Doanh nghiệp Kiểm Thử",
        "doc_type": "Luật",
        "chapter": "Chương II: Thành lập doanh nghiệp",
        "article": "Điều 17",
        "article_title": "Quyền thành lập doanh nghiệp",
        "content": "Tổ chức, cá nhân có quyền thành lập và quản lý doanh nghiệp tại Việt Nam.",
        "extra": [
            "Luật|test-01/2020/QH14|Điều 1",
            # Viện dẫn cả văn bản, không có số Điều -> phải bị bỏ qua.
            "Bộ luật|test-02/2019/QH14",
            # Trỏ tới Điều không tồn tại -> không được sinh link chết.
            "Luật|test-01/2020/QH14|Điều 999",
        ],
    },
    {
        "id": 9_000_004,
        "law_id": "test-02/2019/QH14",
        "law_name": "Bộ luật Lao động Kiểm Thử",
        "doc_type": "Bộ luật",
        "chapter": "Chương III: Hợp đồng lao động",
        "article": "Điều 25",
        "article_title": "Thời gian thử việc",
        "content": "Thời gian thử việc không quá 180 ngày với người quản lý doanh nghiệp.",
        "extra": [],
    },
]


async def seed_articles(session) -> None:
    """Nạp corpus mẫu rồi đồng bộ bảng ``laws``.

    Đi qua chính ``importer`` của production để test không dựa vào một đường ghi
    riêng có thể lệch schema.
    """

    from src.config import get_settings
    from src.services.legal.catalog import sync_law_catalog
    from src.services.legal.importer import import_records

    records = [{**record, "author": "test"} for record in SAMPLE_ARTICLES]
    await import_records(
        records,
        database_url=get_settings().legal_assistant.postgres.sync_database_url,
    )

    await sync_law_catalog(session)
    await session.commit()
