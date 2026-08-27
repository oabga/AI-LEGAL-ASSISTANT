"""Schema cho API tra cứu văn bản pháp luật."""
from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field


class LawOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    law_id: str
    law_name: str
    doc_type: str
    issuer: str | None = None
    category: str
    effective_date: date | None = None
    status: str
    article_count: int


class LawListResponse(BaseModel):
    items: list[LawOut]
    total: int
    # Để UI dựng sẵn dropdown lọc mà không cần gọi thêm endpoint.
    categories: list[str] = Field(default_factory=list)
    doc_types: list[str] = Field(default_factory=list)


class ArticleRef(BaseModel):
    """Viện dẫn chéo đã phân giải, đủ dữ liệu để render thành link."""

    law_id: str
    law_name: str
    article: str
    article_title: str


class ArticleSummary(BaseModel):
    """Một Điều trong cây văn bản, chưa kèm nội dung đầy đủ."""

    id: int
    article: str
    article_title: str


class ChapterNode(BaseModel):
    """Một Chương với danh sách Điều thuộc nó."""

    chapter: str | None
    articles: list[ArticleSummary]


class LawTreeResponse(BaseModel):
    law: LawOut
    chapters: list[ChapterNode]


class ArticleDetail(BaseModel):
    id: int
    law_id: str
    law_name: str
    doc_type: str
    chapter: str | None = None
    article: str
    article_title: str
    content: str
    author: str
    # Viện dẫn chéo đã phân giải; phần không tìm thấy trong corpus bị bỏ.
    related: list[ArticleRef] = Field(default_factory=list)
    # Điều liền trước/liền sau để UI có nút điều hướng trong cùng văn bản.
    previous_article: str | None = None
    next_article: str | None = None


class SearchHit(BaseModel):
    id: int
    law_id: str
    law_name: str
    doc_type: str
    chapter: str | None = None
    article: str
    article_title: str
    content: str
    score: float


class SearchResponse(BaseModel):
    items: list[SearchHit]
    total: int
    query: str
    # article_number | full_text | trigram | empty
    strategy: str
    # Từ khóa để client bôi đậm trên nội dung gốc (khớp kiểu bỏ qua dấu).
    terms: list[str] = Field(default_factory=list)
