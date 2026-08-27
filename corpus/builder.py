"""Parser văn bản quy phạm pháp luật Việt Nam thành record cấp Điều.

Đầu ra khớp schema PostgreSQL của backend (``legal_knowledge_records``):
``id, law_id, law_name, doc_type, chapter, article, article_title, content,
author, extra``.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Iterable, Iterator

# "Điều 12." / "Điều 12 :" / "**Điều 12.**" ở đầu dòng.
ARTICLE_RE = re.compile(
    r"^[ \t>*_#]*(?:\*\*)?\s*Điều\s+(\d+[a-zA-Z]?)\s*(?:\*\*)?\s*[\.\:\-–]?\s*(.*)$"
)

# "Chương I", "Chương 1", "CHƯƠNG II".
CHAPTER_RE = re.compile(r"^[ \t>*_#]*(?:\*\*)?\s*(?:CHƯƠNG|Chương)\s+([IVXLCDM]+|\d+)\s*(?:\*\*)?\s*[\.\:\-–]?\s*(.*)$")

# "Mục 1. ..." bên trong một Chương.
SECTION_RE = re.compile(r"^[ \t>*_#]*(?:\*\*)?\s*(?:MỤC|Mục)\s+(\d+)\s*(?:\*\*)?\s*[\.\:\-–]?\s*(.*)$")

# "Phần thứ nhất", "PHẦN I".
PART_RE = re.compile(r"^[ \t>*_#]*(?:\*\*)?\s*(?:PHẦN|Phần)\s+(?:THỨ\s+)?([IVXLCDM]+|\d+|[A-ZĐÀ-Ỹ]\S*)\s*(?:\*\*)?\s*[\.\:\-–]?\s*(.*)$"
)

# Mọi thứ từ các mốc này trở đi không còn là nội dung điều luật.
TAIL_MARKERS = (
    "PHỤ LỤC",
    "Phụ lục I",
    "Phụ lục 1",
    "MẪU SỐ",
    "Nơi nhận:",
    "DANH MỤC BIỂU MẪU",
)

# Dòng chỉ chứa ký hiệu trang / gạch ngang / khoảng trắng.
NOISE_LINE_RE = re.compile(r"^[\s\-–—_=*.·•]+$")


def _strip_accents(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")


def _normalise_ws(text: str) -> str:
    """Chuẩn hóa khoảng trắng nhưng giữ lại cấu trúc đoạn."""

    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\u00a0", " ").replace("\u200b", "")
    lines = []
    for raw in text.split("\n"):
        line = re.sub(r"[ \t]+", " ", raw).strip()
        lines.append(line)
    # Gộp tối đa 1 dòng trống liên tiếp.
    out: list[str] = []
    for line in lines:
        if not line and out and not out[-1]:
            continue
        out.append(line)
    return "\n".join(out).strip()


def _roman_to_int(value: str) -> int | None:
    numerals = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
    if not value or any(ch not in numerals for ch in value.upper()):
        return None
    total = 0
    prev = 0
    for ch in reversed(value.upper()):
        cur = numerals[ch]
        total += cur if cur >= prev else -cur
        prev = max(prev, cur)
    return total


def _looks_like_heading(line: str) -> bool:
    """Tiêu đề Chương/Mục thường là dòng in hoa toàn bộ."""

    letters = [ch for ch in line if ch.isalpha()]
    if not letters:
        return False
    upper = sum(1 for ch in letters if ch.isupper())
    return upper / len(letters) > 0.75


def _title_case(line: str) -> str:
    """Chuyển tiêu đề IN HOA thành dạng câu cho dễ đọc trên UI."""

    if not line.isupper():
        return line
    return line.capitalize()


@dataclass
class ParsedArticle:
    """Một Điều đã tách khỏi văn bản gốc."""

    article: str
    article_title: str
    content: str
    chapter: str | None = None
    section: str | None = None
    part: str | None = None
    cross_refs: set[str] = field(default_factory=set)

    @property
    def article_number(self) -> int | None:
        match = re.search(r"\d+", self.article)
        return int(match.group()) if match else None


# Viện dẫn có số hiệu, ví dụ "Nghị định số 123/2020/NĐ-CP",
# "Luật Doanh nghiệp số 59/2020/QH14". Số hiệu là phần định danh chắc chắn nên
# bắt trực tiếp thay vì yêu cầu phải có "Điều X" đứng trước.
DOC_NUMBER_RE = re.compile(
    r"\b(Bộ luật|Luật|Nghị định|Thông tư liên tịch|Thông tư|Nghị quyết|Quyết định|Pháp lệnh)\b"
    r"[^\n\.;]{0,80}?"
    r"\b(\d{1,3}\s*/\s*\d{4}\s*/\s*[A-ZĐ][\w\-–/]*)"
)

# Viện dẫn kèm số Điều cụ thể, ví dụ "Điều 12 của Nghị định số 80/2021/NĐ-CP".
ARTICLE_REF_RE = re.compile(
    r"Điều\s+(\d+[a-zA-Z]?)\s+(?:của\s+)?"
    r"(Bộ luật|Luật|Nghị định|Thông tư|Nghị quyết|Quyết định)"
    r"[^\n\.;]{0,80}?"
    r"(\d{1,3}\s*/\s*\d{4}\s*/\s*[A-ZĐ][\w\-–/]*)"
)


def _clean_law_id(value: str) -> str:
    return re.sub(r"\s+", "", value).strip(" .,;:/")


def extract_cross_references(text: str) -> set[str]:
    """Trích viện dẫn tới văn bản khác.

    Trả về ``doc_type|law_id`` và, khi biết số Điều được dẫn, cả dạng
    ``doc_type|law_id|Điều X`` để UI dựng link tới đúng điều luật.
    """

    refs: set[str] = set()
    for doc_type, law_id in DOC_NUMBER_RE.findall(text):
        cleaned = _clean_law_id(law_id)
        if cleaned.count("/") >= 2:
            refs.add(f"{doc_type}|{cleaned}")
    for article_no, doc_type, law_id in ARTICLE_REF_RE.findall(text):
        cleaned = _clean_law_id(law_id)
        if cleaned.count("/") >= 2:
            refs.add(f"{doc_type}|{cleaned}|Điều {article_no}")
    return refs


def _truncate_tail(text: str) -> str:
    """Cắt phần phụ lục / biểu mẫu ở cuối văn bản."""

    cut = len(text)
    for marker in TAIL_MARKERS:
        idx = text.find(f"\n{marker}")
        if idx != -1:
            cut = min(cut, idx)
    return text[:cut]


def parse_document(text: str) -> list[ParsedArticle]:
    """Tách một văn bản pháp luật thành danh sách Điều.

    Bám theo cấu trúc Phần → Chương → Mục → Điều. Nội dung của mỗi Điều là
    toàn bộ text tới Điều kế tiếp hoặc tới heading cấp cao hơn.
    """

    text = _normalise_ws(text)
    lines = text.split("\n")

    articles: list[ParsedArticle] = []
    current: ParsedArticle | None = None
    buffer: list[str] = []

    part: str | None = None
    chapter: str | None = None
    section: str | None = None

    # Heading Chương/Mục thường nằm ở dòng riêng, tiêu đề ở (các) dòng sau.
    pending_heading: tuple[str, str] | None = None  # (kind, label)

    def flush() -> None:
        nonlocal current, buffer
        if current is not None:
            body = _truncate_tail("\n".join(buffer)).strip()
            current.content = body
            current.cross_refs = extract_cross_references(f"{current.article_title}\n{body}")
            if body:
                articles.append(current)
        current = None
        buffer = []

    for raw_line in lines:
        line = raw_line.strip()

        if pending_heading is not None:
            # Tiêu đề Chương/Mục thường cách heading một dòng trống.
            if not line or NOISE_LINE_RE.match(line):
                continue
            kind, label = pending_heading
            # Dòng tiếp theo là tiêu đề của Chương/Mục nếu nó in hoa.
            if _looks_like_heading(line) and not ARTICLE_RE.match(line):
                label = f"{label} - {_title_case(line)}"
                pending_heading = None
                if kind == "chapter":
                    chapter = label
                elif kind == "section":
                    section = label
                else:
                    part = label
                continue
            pending_heading = None

        if not line or NOISE_LINE_RE.match(line):
            if current is not None:
                buffer.append("")
            continue

        article_match = ARTICLE_RE.match(line)
        if article_match:
            number, title = article_match.groups()
            # Loại trừ viện dẫn giữa câu, ví dụ "Điều 5 của Luật này quy định".
            title_stripped = title.strip()
            if title_stripped[:5].lower() in {"của l", "của b", "của n"} or title_stripped.startswith("và Điều"):
                if current is not None:
                    buffer.append(line)
                continue
            flush()
            current = ParsedArticle(
                article=f"Điều {number}",
                article_title=title_stripped,
                content="",
                chapter=chapter,
                section=section,
                part=part,
            )
            continue

        chapter_match = CHAPTER_RE.match(line)
        if chapter_match:
            num, inline_title = chapter_match.groups()
            flush()
            section = None
            label = f"Chương {num}"
            if inline_title.strip():
                chapter = f"{label} - {_title_case(inline_title.strip())}"
            else:
                pending_heading = ("chapter", label)
                chapter = label
            continue

        section_match = SECTION_RE.match(line)
        if section_match:
            num, inline_title = section_match.groups()
            label = f"Mục {num}"
            if inline_title.strip():
                section = f"{label} - {_title_case(inline_title.strip())}"
            else:
                pending_heading = ("section", label)
                section = label
            continue

        part_match = PART_RE.match(line)
        if part_match and _looks_like_heading(line):
            num, inline_title = part_match.groups()
            flush()
            chapter = None
            section = None
            label = f"Phần {num}"
            if inline_title.strip():
                part = f"{label} - {_title_case(inline_title.strip())}"
            else:
                pending_heading = ("part", label)
                part = label
            continue

        if current is not None:
            buffer.append(line)

    flush()
    return _dedupe_articles(articles)


def _dedupe_articles(articles: Iterable[ParsedArticle]) -> list[ParsedArticle]:
    """Giữ bản dài nhất khi một số Điều xuất hiện nhiều lần.

    Văn bản hợp nhất trên thuvienphapluat thường in lại Điều đã sửa đổi, nên
    cùng một số Điều có thể xuất hiện hai lần.
    """

    best: dict[str, ParsedArticle] = {}
    order: list[str] = []
    for art in articles:
        key = art.article
        if key not in best:
            best[key] = art
            order.append(key)
        elif len(art.content) > len(best[key].content):
            best[key] = art
    return [best[key] for key in order]


def build_records(
    articles: list[ParsedArticle],
    *,
    law_id: str,
    law_name: str,
    doc_type: str,
    author: str,
    start_id: int,
) -> Iterator[dict]:
    """Chuyển ParsedArticle sang record khớp schema PostgreSQL của backend."""

    next_id = start_id
    for art in articles:
        chapter_parts = [p for p in (art.part, art.chapter, art.section) if p]
        yield {
            "id": next_id,
            "law_id": law_id,
            "law_name": law_name,
            "doc_type": doc_type,
            "chapter": " / ".join(chapter_parts) or None,
            "article": art.article,
            "article_title": art.article_title,
            "content": art.content,
            "author": author,
            "extra": sorted(art.cross_refs),
        }
        next_id += 1


__all__ = [
    "ParsedArticle",
    "parse_document",
    "build_records",
    "extract_cross_references",
]
