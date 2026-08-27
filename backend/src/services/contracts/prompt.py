"""Prompt chấm rủi ro điều khoản hợp đồng."""
from __future__ import annotations

import json

from src.schemas.legal import LegalArticle

CLAUSE_REVIEW_SYSTEM_PROMPT = """Bạn là luật sư doanh nghiệp rà soát hợp đồng cho doanh nghiệp nhỏ và vừa tại Việt Nam.

Nhiệm vụ: đánh giá rủi ro pháp lý của MỘT điều khoản hợp đồng, chỉ dựa trên các căn cứ pháp lý được cung cấp.

Nguyên tắc:
- Chỉ kết luận trái luật / thiếu sót khi có căn cứ pháp lý trong phần CĂN CỨ. Không có căn cứ phù hợp thì để risk_level là "thấp" và nói rõ là chưa đủ cơ sở.
- Không bịa số điều, mức phạt, thời hạn hoặc tên văn bản.
- Đánh giá theo góc nhìn bảo vệ doanh nghiệp nhỏ và vừa đang ký hợp đồng này.
- issue và recommendation viết bằng tiếng Việt, ngắn gọn, cụ thể, hướng hành động.

Mức rủi ro:
- "cao": trái quy định bắt buộc, hoặc gây thiệt hại/tranh chấp lớn (ví dụ thiếu điều khoản bắt buộc, mức phạt vượt trần luật cho phép, đơn phương bất lợi rõ rệt).
- "trung bình": chưa trái luật nhưng thiếu rõ ràng, dễ tranh chấp, hoặc bất lợi cần thương lượng lại.
- "thấp": phù hợp quy định, hoặc chỉ là vấn đề diễn đạt.

Chỉ trả về DUY NHẤT một JSON object, không markdown, không giải thích thêm:
{"risk_level": "cao|trung bình|thấp", "issue": "...", "recommendation": "..."}
"""

CLAUSE_REVIEW_USER_PROMPT = """ĐIỀU KHOẢN HỢP ĐỒNG{clause_label}:
\"\"\"
{clause_text}
\"\"\"

CĂN CỨ PHÁP LÝ ĐÃ TRUY HỒI:
{legal_context}

Trả về JSON đánh giá rủi ro của điều khoản trên."""

SUMMARY_SYSTEM_PROMPT = """Bạn là luật sư doanh nghiệp tổng hợp kết quả rà soát hợp đồng cho doanh nghiệp nhỏ và vừa.

Viết bản tóm tắt tiếng Việt 4-6 câu cho chủ doanh nghiệp không có nền tảng pháp lý:
- Câu đầu nêu mức độ rủi ro tổng thể của hợp đồng.
- Nêu 2-3 vấn đề đáng lo nhất, gọi tên điều khoản cụ thể.
- Kết bằng việc cần làm trước khi ký.

Chỉ dựa trên danh sách phát hiện được cung cấp. Không thêm nhận định mới, không bịa điều luật. Không dùng markdown.
"""

NO_LEGAL_CONTEXT = "(Không truy hồi được điều luật liên quan cho điều khoản này.)"


def build_clause_messages(
    clause_title: str | None,
    clause_text: str,
    articles: list[LegalArticle],
) -> tuple[str, str]:
    """Dựng (system, user) prompt để chấm rủi ro một điều khoản."""

    if articles:
        legal_context = "\n\n".join(
            f"[{index}] {article.law_name} - {article.article}"
            f"{f' ({article.article_title})' if article.article_title else ''}\n"
            f"{' '.join(article.content.split())[:1500]}"
            for index, article in enumerate(articles, start=1)
        )
    else:
        legal_context = NO_LEGAL_CONTEXT

    return CLAUSE_REVIEW_SYSTEM_PROMPT, CLAUSE_REVIEW_USER_PROMPT.format(
        clause_label=f" ({clause_title})" if clause_title else "",
        clause_text=" ".join(clause_text.split())[:4000],
        legal_context=legal_context,
    )


def build_summary_messages(findings: list[dict], clause_count: int) -> tuple[str, str]:
    """Dựng (system, user) prompt để tóm tắt toàn bộ kết quả soát xét."""

    payload = json.dumps(
        [
            {
                "điều khoản": finding.get("clause_title") or f"Điều khoản {finding['position']}",
                "mức rủi ro": finding["risk_level"],
                "vấn đề": finding["issue"],
                "căn cứ": finding.get("legal_refs", [])[:2],
            }
            for finding in findings
        ],
        ensure_ascii=False,
        indent=2,
    )
    user_prompt = (
        f"Hợp đồng có {clause_count} điều khoản được rà soát.\n\n"
        f"DANH SÁCH PHÁT HIỆN:\n{payload}\n\nViết bản tóm tắt."
    )
    return SUMMARY_SYSTEM_PROMPT, user_prompt
