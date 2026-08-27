"""Chấm rủi ro từng điều khoản hợp đồng qua legal RAG + LLM.

Mỗi điều khoản được dùng làm truy vấn để retrieval tìm quy định liên quan, rồi
LLM đánh giá điều khoản đó *chỉ dựa trên* căn cứ vừa truy hồi. Nhờ vậy mọi phát
hiện đều kèm trích dẫn Điều luật để người dùng tự kiểm chứng.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

from src.config import get_settings
from src.models.enums import RiskLevel
from src.schemas.legal import LegalArticle, RetrievalQuery
from src.services.contracts.extract import Clause
from src.services.contracts.prompt import build_clause_messages, build_summary_messages

logger = logging.getLogger(__name__)

# Trọng số quy risk_score về thang 0-100.
RISK_WEIGHTS = {RiskLevel.HIGH: 100, RiskLevel.MEDIUM: 55, RiskLevel.LOW: 10}

RISK_ALIASES = {
    "cao": RiskLevel.HIGH,
    "high": RiskLevel.HIGH,
    "trung bình": RiskLevel.MEDIUM,
    "trung binh": RiskLevel.MEDIUM,
    "medium": RiskLevel.MEDIUM,
    "thấp": RiskLevel.LOW,
    "thap": RiskLevel.LOW,
    "low": RiskLevel.LOW,
}

JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


def parse_risk_level(value: Any) -> RiskLevel:
    """Chuẩn hóa mức rủi ro do LLM trả về; không nhận diện được thì coi là thấp."""

    return RISK_ALIASES.get(str(value or "").strip().lower(), RiskLevel.LOW)


def parse_clause_verdict(raw: str) -> dict[str, Any]:
    """Bóc JSON từ output LLM, chịu được trường hợp bị bọc trong markdown."""

    match = JSON_OBJECT_RE.search(raw or "")
    if match:
        try:
            payload = json.loads(match.group(0))
        except json.JSONDecodeError:
            payload = {}
    else:
        payload = {}

    issue = str(payload.get("issue") or "").strip()
    if not issue:
        # Không parse được thì vẫn giữ lại nội dung thô để người dùng thấy,
        # thay vì âm thầm bỏ điều khoản này.
        issue = (raw or "").strip()[:500] or "Không đánh giá được điều khoản này."
    return {
        "risk_level": parse_risk_level(payload.get("risk_level")),
        "issue": issue,
        "recommendation": (str(payload.get("recommendation") or "").strip() or None),
    }


def compute_risk_score(findings: list[dict]) -> int:
    """Điểm rủi ro 0-100 của cả hợp đồng.

    Lấy mức cao nhất làm nền rồi cộng thêm theo số lượng phát hiện nặng: một
    điều khoản trái luật đã đủ khiến hợp đồng rủi ro cao, nhưng nhiều điều khoản
    cùng có vấn đề thì phải nặng hơn một điều khoản đơn lẻ.
    """

    if not findings:
        return 0
    weights = [RISK_WEIGHTS[finding["risk_level"]] for finding in findings]
    highest = max(weights)
    high_count = sum(1 for finding in findings if finding["risk_level"] == RiskLevel.HIGH)
    medium_count = sum(1 for finding in findings if finding["risk_level"] == RiskLevel.MEDIUM)
    score = highest + (high_count - 1) * 5 + medium_count * 2 if high_count else highest + medium_count * 2
    return max(0, min(100, round(score)))


def _retrieve_articles(registry, clause: Clause, top_k: int) -> list[LegalArticle]:
    """Truy hồi quy định liên quan tới một điều khoản.

    Dùng tiêu đề + phần đầu nội dung điều khoản làm truy vấn: tiêu đề mang chủ
    đề pháp lý, phần nội dung mang chi tiết để phân biệt các điều khoản cùng tên.
    """

    question = " ".join(filter(None, [clause.title, clause.text[:1200]]))
    query = RetrievalQuery(
        question=question,
        original_question=question,
        query_variants=[question],
        search_spaces=registry.list_databases() or ["default"],
        top_k=top_k,
    )
    try:
        candidates = registry.search(query)
    except Exception:
        logger.exception("Retrieval lỗi cho điều khoản %s", clause.position)
        return []
    return [candidate.article for candidate in candidates]


async def review_clauses(
    clauses: list[Clause],
    *,
    registry,
    llm,
) -> list[dict]:
    """Chấm rủi ro toàn bộ điều khoản, chạy song song có giới hạn."""

    settings = get_settings().legal_assistant.contract_review
    semaphore = asyncio.Semaphore(settings.max_concurrency)

    async def review_one(clause: Clause) -> dict:
        async with semaphore:
            # Retrieval là code đồng bộ (Chroma/BM25), đẩy sang thread để không
            # chặn event loop khi soát xét nhiều điều khoản.
            articles = await asyncio.to_thread(
                _retrieve_articles, registry, clause, settings.retrieval_top_k
            )
            system_prompt, user_prompt = build_clause_messages(
                clause.title, clause.text, articles
            )
            try:
                raw = await _invoke(llm, system_prompt, user_prompt)
                verdict = parse_clause_verdict(raw)
            except Exception as exc:
                logger.exception("LLM lỗi khi chấm điều khoản %s", clause.position)
                verdict = {
                    "risk_level": RiskLevel.LOW,
                    "issue": f"Không đánh giá được điều khoản này: {exc}",
                    "recommendation": None,
                }
            return {
                "position": clause.position,
                "clause_title": clause.title,
                "clause_text": clause.text,
                "legal_refs": [article.article_ref for article in articles],
                **verdict,
            }

    findings = await asyncio.gather(*(review_one(clause) for clause in clauses))
    return sorted(findings, key=lambda item: item["position"])


async def summarize(findings: list[dict], clause_count: int, *, llm) -> str:
    """Tóm tắt kết quả soát xét cho người không có nền tảng pháp lý."""

    notable = [
        finding
        for finding in findings
        if finding["risk_level"] in {RiskLevel.HIGH, RiskLevel.MEDIUM}
    ]
    if not notable:
        return (
            f"Đã rà soát {clause_count} điều khoản và không phát hiện rủi ro pháp lý "
            "đáng kể dựa trên kho văn bản hiện có. Vẫn nên đối chiếu lại các mốc "
            "thời hạn và số tiền trong hợp đồng trước khi ký."
        )

    system_prompt, user_prompt = build_summary_messages(notable, clause_count)
    try:
        return (await _invoke(llm, system_prompt, user_prompt)).strip()
    except Exception:
        logger.exception("LLM lỗi khi tóm tắt kết quả soát xét")
        high = sum(1 for item in notable if item["risk_level"] == RiskLevel.HIGH)
        medium = len(notable) - high
        return (
            f"Đã rà soát {clause_count} điều khoản, phát hiện {high} điều khoản rủi ro cao "
            f"và {medium} điều khoản rủi ro trung bình. Xem chi tiết từng phát hiện ở bảng dưới."
        )


async def _invoke(llm, system_prompt: str, user_prompt: str) -> str:
    """Gọi LLM bằng SystemMessage/HumanMessage, fallback về plain prompt."""

    try:
        from langchain_core.messages import HumanMessage, SystemMessage
    except ImportError:
        return await llm.ainvoke(f"{system_prompt}\n\n{user_prompt}")

    if hasattr(llm, "ainvoke_messages"):
        return await llm.ainvoke_messages(
            [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]
        )
    return await llm.ainvoke(f"{system_prompt}\n\n{user_prompt}")
