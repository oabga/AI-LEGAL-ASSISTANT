"""Smoke test trích text + cắt điều khoản + upload hợp đồng.

Phần chấm rủi ro cần LLM nên chỉ kiểm tra bằng LLM giả, để logic parse/score
được xác minh mà không tốn quota.
"""
from __future__ import annotations

import asyncio
import io
import uuid

import httpx
from fastapi import FastAPI

from src.config import get_settings
from src.core.rate_limit import install_rate_limiter
from src.models.enums import RiskLevel
from src.routers import auth_router, documents_router
from src.services.contracts.extract import detect_mime, extract_text, split_clauses
from src.services.contracts.reviewer import (
    compute_risk_score,
    parse_clause_verdict,
    review_clauses,
    summarize,
)

CONTRACT = """HỢP ĐỒNG LAO ĐỘNG
Số: 12/2026/HĐLĐ

Hôm nay, ngày 01 tháng 03 năm 2026, tại Hà Nội, chúng tôi gồm:
BÊN A (Người sử dụng lao động): Công ty TNHH Thương mại Bình Minh
Mã số thuế: 0101234567. Địa chỉ: số 10 phố Láng Hạ, quận Đống Đa, Hà Nội.
BÊN B (Người lao động): Nguyễn Văn A, sinh năm 1995, CCCD số 001095012345.

Điều 1. Loại hợp đồng và thời hạn
Hai bên thống nhất ký hợp đồng lao động xác định thời hạn 36 tháng, kể từ ngày 01/03/2026
đến ngày 28/02/2029. Thời gian thử việc là 3 tháng với mức lương bằng 70% lương chính thức.

Điều 2. Công việc và địa điểm làm việc
Bên B đảm nhận vị trí nhân viên kinh doanh tại trụ sở Bên A. Bên A có quyền điều chuyển
Bên B sang bất kỳ vị trí hoặc địa điểm nào khác mà không cần báo trước và không cần sự
đồng ý của Bên B.

Điều 3. Thời giờ làm việc
Bên B làm việc 08 giờ mỗi ngày, từ thứ Hai đến thứ Bảy. Khi có yêu cầu công việc, Bên B
phải làm thêm giờ theo yêu cầu của Bên A, tối đa 500 giờ mỗi năm, và tiền làm thêm giờ
được tính bằng 100% tiền lương giờ bình thường.

Điều 4. Tiền lương và thời hạn trả lương
Mức lương chính thức là 12.000.000 đồng/tháng. Bên A trả lương chậm nhất vào ngày 15
của tháng tiếp theo. Trường hợp Bên A chậm trả lương, Bên B không có quyền yêu cầu bồi
thường hoặc tính lãi.

Điều 5. Bảo hiểm xã hội
Bên A đóng bảo hiểm xã hội, bảo hiểm y tế, bảo hiểm thất nghiệp cho Bên B theo quy định
của pháp luật, trên mức lương ghi trong hợp đồng.

Điều 6. Chấm dứt hợp đồng
Bên A có quyền đơn phương chấm dứt hợp đồng bất kỳ lúc nào mà không cần báo trước và
không phải trả trợ cấp. Bên B muốn nghỉ việc phải báo trước 90 ngày, nếu không phải đền
bù cho Bên A 03 tháng tiền lương.

Điều 7. Bảo mật và cam kết không cạnh tranh
Bên B không được làm việc cho bất kỳ doanh nghiệp nào cùng ngành trong 05 năm sau khi
chấm dứt hợp đồng, trên toàn bộ lãnh thổ Việt Nam, không kèm bất kỳ khoản bù đắp nào.

Điều 8. Giải quyết tranh chấp
Mọi tranh chấp phát sinh được giải quyết thông qua thương lượng. Nếu không thương lượng
được, tranh chấp sẽ do Tòa án nơi Bên A đặt trụ sở giải quyết theo quy định pháp luật.
"""


class FakeLLM:
    """LLM giả trả JSON hợp lệ, đủ để kiểm tra parse và tính điểm."""

    def __init__(self) -> None:
        self.calls = 0

    async def ainvoke_messages(self, messages) -> str:
        self.calls += 1
        content = str(getattr(messages[-1], "content", ""))
        if "Viết bản tóm tắt" in content:
            return "Hợp đồng có nhiều điều khoản bất lợi cho người lao động và cần sửa trước khi ký."
        if "điều chuyển" in content or "chấm dứt hợp đồng bất kỳ lúc nào" in content:
            return (
                '```json\n{"risk_level": "cao", "issue": "Điều khoản trái quy định về '
                'điều chuyển và chấm dứt hợp đồng.", "recommendation": "Sửa theo Bộ luật '
                'Lao động 2019."}\n```'
            )
        if "làm thêm giờ" in content or "chậm trả lương" in content:
            return '{"risk_level": "trung bình", "issue": "Cần làm rõ mức làm thêm giờ.", "recommendation": "Đối chiếu trần giờ làm thêm."}'
        return '{"risk_level": "thấp", "issue": "Điều khoản phù hợp quy định.", "recommendation": null}'


class FakeRegistry:
    """Registry giả để chạy pipeline không cần Chroma/BM25."""

    def list_databases(self):
        return ["default"]

    def search(self, query):
        from src.schemas.legal import LegalArticle, RetrievedCandidate

        article = LegalArticle(
            id="1",
            law_id="45/2019/QH14",
            law_name="Bộ luật Lao động",
            doc_type="Bộ luật",
            article="Điều 29",
            article_title="Chuyển người lao động làm công việc khác",
            content="Khi gặp khó khăn đột xuất, người sử dụng lao động được tạm thời chuyển...",
        )
        return [RetrievedCandidate(article=article, score=0.9)]


def test_extract_and_split() -> None:
    print("=== Trích text và cắt điều khoản ===")
    assert detect_mime("hop-dong.docx", "application/octet-stream").endswith("document")
    assert detect_mime("hop-dong.pdf", None) == "application/pdf"
    try:
        detect_mime("anh.jpg", "image/jpeg")
        raise AssertionError("phải chặn định dạng ảnh")
    except Exception as exc:
        print("chặn .jpg ->", str(exc)[:60])

    text = extract_text(CONTRACT.encode("utf-8"), "text/plain")
    clauses = split_clauses(text, max_clauses=60)
    print(f"tách được {len(clauses)} điều khoản:")
    for clause in clauses:
        print(f"  #{clause.position} {clause.title or '(phần mở đầu)'} — {len(clause.text)} ký tự")
    titles = [c.title for c in clauses if c.title]
    assert len(titles) == 8, f"phải tách đúng 8 điều, thực tế {len(titles)}"
    assert "Điều 4" in titles[3], titles

    # Hợp đồng viết liền không có tiêu đề vẫn phải cắt được.
    blob = "\n\n".join(["Nội dung đoạn văn dài để vượt ngưỡng gộp. " * 5] * 4)
    fallback = split_clauses(blob, max_clauses=60)
    print("fallback cắt theo đoạn ->", len(fallback), "khối")
    assert len(fallback) > 1

    # Giới hạn số điều khoản phải được tôn trọng.
    capped = split_clauses(text, max_clauses=3)
    assert len(capped) == 3, len(capped)
    print("max_clauses=3 ->", len(capped), "điều khoản")


def test_scoring() -> None:
    print("\n=== Parse verdict và tính điểm rủi ro ===")
    wrapped = parse_clause_verdict('```json\n{"risk_level":"cao","issue":"X","recommendation":"Y"}\n```')
    assert wrapped["risk_level"] == RiskLevel.HIGH, wrapped
    print("parse JSON bọc markdown ->", wrapped["risk_level"])

    garbage = parse_clause_verdict("model trả về văn bản tự do không phải JSON")
    assert garbage["risk_level"] == RiskLevel.LOW
    assert garbage["issue"], "phải giữ lại nội dung thô"
    print("parse output không phải JSON ->", garbage["risk_level"], "|", garbage["issue"][:40])

    assert compute_risk_score([]) == 0
    low_only = compute_risk_score([{"risk_level": RiskLevel.LOW}])
    one_high = compute_risk_score([{"risk_level": RiskLevel.HIGH}])
    three_high = compute_risk_score([{"risk_level": RiskLevel.HIGH}] * 3)
    mixed = compute_risk_score(
        [{"risk_level": RiskLevel.MEDIUM}, {"risk_level": RiskLevel.LOW}]
    )
    print(f"score: rỗng=0 thấp={low_only} 1cao={one_high} 3cao={three_high} trung bình={mixed}")
    assert low_only < mixed < one_high <= three_high <= 100


async def test_review_pipeline() -> None:
    print("\n=== Pipeline chấm rủi ro (LLM giả) ===")
    clauses = split_clauses(extract_text(CONTRACT.encode(), "text/plain"), max_clauses=60)
    llm = FakeLLM()
    findings = await review_clauses(clauses, registry=FakeRegistry(), llm=llm)
    assert len(findings) == len(clauses)
    assert [f["position"] for f in findings] == sorted(f["position"] for f in findings)
    assert all(f["legal_refs"] for f in findings), "mỗi finding phải có trích dẫn"
    print(f"chấm {len(findings)} điều khoản, {llm.calls} lần gọi LLM")
    for finding in findings:
        if finding["risk_level"] != RiskLevel.LOW:
            print(
                f"  [{finding['risk_level']}] #{finding['position']}"
                f" {finding['clause_title'] or 'mở đầu'} <- {finding['legal_refs'][0]}"
            )
    print("risk_score =", compute_risk_score(findings))
    print("summary:", (await summarize(findings, len(clauses), llm=llm))[:90])


def build_app() -> FastAPI:
    app = FastAPI()
    app.state.settings = get_settings()
    install_rate_limiter(app, app.state.settings)
    app.include_router(auth_router)
    app.include_router(documents_router)
    return app


async def test_upload_api() -> None:
    print("\n=== API upload ===")
    app = build_app()
    email = f"doc-{uuid.uuid4().hex[:8]}@example.com"
    tax_code = f"03{uuid.uuid4().int % 10**8:08d}"
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test", timeout=60) as client:
        registered = await client.post(
            "/api/v1/auth/register",
            json={
                "email": email,
                "password": "SmokeTest#2026",
                "full_name": "Nhân Sự",
                "role": "hr",
                "organization": {"name": "Công ty Hợp Đồng", "tax_code": tax_code},
            },
        )
        assert registered.status_code == 201, registered.text
        headers = {"Authorization": f"Bearer {registered.json()['tokens']['access_token']}"}

        uploaded = await client.post(
            "/api/v1/documents",
            files={"file": ("hop-dong-lao-dong.txt", io.BytesIO(CONTRACT.encode()), "text/plain")},
            headers=headers,
        )
        assert uploaded.status_code == 201, uploaded.text
        document = uploaded.json()
        print(
            f"upload -> {document['status']}, {document['size_bytes']} byte,"
            f" trích {document['text_length']} ký tự"
        )

        rejected = await client.post(
            "/api/v1/documents",
            files={"file": ("anh.jpg", io.BytesIO(b"\xff\xd8\xff" * 40), "image/jpeg")},
            headers=headers,
        )
        assert rejected.status_code == 400, rejected.status_code
        print("upload .jpg ->", rejected.status_code, rejected.json()["detail"][:50])

        empty = await client.post(
            "/api/v1/documents",
            files={"file": ("rong.txt", io.BytesIO(b""), "text/plain")},
            headers=headers,
        )
        assert empty.status_code == 400, empty.status_code
        print("upload file rỗng ->", empty.status_code)

        short = await client.post(
            "/api/v1/documents",
            files={"file": ("ngan.txt", io.BytesIO("Xin chào".encode()), "text/plain")},
            headers=headers,
        )
        assert short.status_code == 400, short.status_code
        print("upload nội dung quá ngắn ->", short.status_code)

        listing = await client.get("/api/v1/documents", headers=headers)
        assert listing.status_code == 200, listing.text
        print("list documents ->", listing.json()["total"])

        detail = await client.get(f"/api/v1/documents/{document['id']}", headers=headers)
        assert detail.status_code == 200, detail.text

        missing = await client.get(f"/api/v1/documents/{uuid.uuid4()}", headers=headers)
        assert missing.status_code == 404, missing.status_code
        print("document không tồn tại ->", missing.status_code)

        deleted = await client.delete(f"/api/v1/documents/{document['id']}", headers=headers)
        assert deleted.status_code == 204, deleted.status_code
        print("delete document ->", deleted.status_code)

    await cleanup(email)


async def cleanup(email: str) -> None:
    from sqlalchemy import delete, select

    from src.core.database import get_session_factory
    from src.models import Organization, User

    async with get_session_factory()() as session:
        rows = (
            await session.execute(
                select(User.id, User.organization_id).where(User.email == email)
            )
        ).all()
        if rows:
            await session.execute(delete(User).where(User.id.in_([r[0] for r in rows])))
        org_ids = [r[1] for r in rows if r[1]]
        if org_ids:
            await session.execute(delete(Organization).where(Organization.id.in_(org_ids)))
        await session.commit()


async def main() -> int:
    test_extract_and_split()
    test_scoring()
    await test_review_pipeline()
    await test_upload_api()
    print("\nSMOKE OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
