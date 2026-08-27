"""Wrapper cho embedding endpoint OpenAI-compatible.

Khác với bản gốc chỉ nhắm vào vLLM local, client này phải chịu được provider
cloud: có rate limit, có lỗi tạm thời, và hỗ trợ giảm số chiều vector
(Matryoshka) để index nhẹ hơn.
"""
from __future__ import annotations

import logging
import random
import time
from functools import lru_cache
from typing import Any, Callable, Iterable, TypeVar

from src.config import settings

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Chuỗi xuất hiện trong lỗi đáng retry (rate limit / lỗi tạm thời phía provider).
RETRYABLE_HINTS = (
    "429",
    "rate limit",
    "resource_exhausted",
    "quota",
    "500",
    "502",
    "503",
    "504",
    "timeout",
    "timed out",
    "connection",
    "temporarily unavailable",
    "overloaded",
)


def _is_retryable(exc: Exception) -> bool:
    message = str(exc).lower()
    return any(hint in message for hint in RETRYABLE_HINTS)


class EmbeddingsClient:
    """Client embedding dùng LangChain ``OpenAIEmbeddings``.

    Endpoint có thể là server local hoặc provider cloud, miễn là API tương thích
    OpenAI. Với ``base_url`` kết thúc bằng ``/v1``, LangChain gọi
    ``POST {base_url}/embeddings``.

    Ba lớp bảo vệ khi index corpus lớn:

    1. cắt text theo ``embeddings.max_input_tokens`` để không vượt context;
    2. chia batch theo ``embeddings.batch_size`` để request không quá lớn;
    3. exponential backoff + jitter khi provider trả 429/5xx.
    """

    def __init__(self):
        try:
            from langchain_openai import OpenAIEmbeddings
        except ImportError as exc:  # pragma: no cover - guard khi thiếu dependency
            raise RuntimeError("Install langchain-openai to use the embeddings endpoint") from exc

        config = settings.embeddings
        if not (config.api_key or "").strip():
            raise RuntimeError(
                "Thiếu LLM_API_KEY (hoặc EMBEDDINGS_API_KEY). "
                "Không thể gọi Gemini để dựng vector index. "
                "Đăng nhập, tra cứu văn bản và lịch tuân thủ vẫn dùng được."
            )
        self.max_input_tokens = config.max_input_tokens
        self.batch_size = config.batch_size
        self.max_retries = config.max_retries
        self.retry_base_delay = config.retry_base_delay
        self.retry_max_delay = config.retry_max_delay
        self.model = config.model
        self.dimensions = config.dimensions
        self._encoding = self._load_encoding(config.tokenizer_encoding)

        kwargs: dict[str, Any] = {
            "model": config.model,
            "base_url": config.base_url,
            "api_key": config.api_key,
            # Server nhận raw text, không nhận token id đã encode sẵn của OpenAI.
            "tiktoken_enabled": False,
            "check_embedding_ctx_length": False,
            "timeout": config.request_timeout,
            # Tự quản lý retry để log được và dùng chung policy cho mọi provider.
            "max_retries": 0,
        }
        if config.dimensions:
            kwargs["dimensions"] = config.dimensions
        self.embeddings = OpenAIEmbeddings(**kwargs)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed nhiều record pháp luật khi build vector database."""

        prepared = [self._truncate_text(text) for text in texts]
        vectors: list[list[float]] = []
        for batch in self._chunks(prepared, self.batch_size):
            vectors.extend(
                self._with_retry(
                    lambda: self.embeddings.embed_documents(batch),
                    what=f"embed_documents({len(batch)} text)",
                )
            )
        return vectors

    def embed_query(self, text: str) -> list[float]:
        """Embed một query đã rewrite/HyDE để search vector store."""

        prepared = self._truncate_text(text)
        return self._with_retry(
            lambda: self.embeddings.embed_query(prepared),
            what="embed_query",
        )

    @staticmethod
    def _chunks(items: list[T], size: int) -> Iterable[list[T]]:
        for start in range(0, len(items), size):
            yield items[start : start + size]

    def _with_retry(self, action: Callable[[], T], *, what: str) -> T:
        """Chạy ``action`` với exponential backoff khi provider giới hạn tần suất."""

        attempt = 0
        while True:
            try:
                return action()
            except Exception as exc:
                attempt += 1
                if attempt > self.max_retries or not _is_retryable(exc):
                    raise RuntimeError(
                        f"Embedding endpoint lỗi khi {what} (model {self.model}): {exc}"
                    ) from exc
                # Jitter tránh nhiều worker cùng retry đồng thời.
                delay = min(self.retry_base_delay * (2 ** (attempt - 1)), self.retry_max_delay)
                delay *= 0.5 + random.random()
                logger.warning(
                    "Embedding %s bị chặn (lần %d/%d), chờ %.1fs: %s",
                    what,
                    attempt,
                    self.max_retries,
                    delay,
                    exc,
                )
                time.sleep(delay)

    def _load_encoding(self, encoding_name: str) -> Any | None:
        """Nạp tokenizer cục bộ để cắt token trước khi gửi embedding endpoint."""

        try:
            import tiktoken

            return tiktoken.get_encoding(encoding_name)
        except Exception:  # pragma: no cover - fallback khi thiếu tiktoken/encoding
            return None

    def _truncate_text(self, text: str) -> str:
        """Cắt phần cuối text nếu vượt giới hạn token embedding."""

        if not text or self.max_input_tokens <= 0:
            return text
        if self._encoding is None:
            # Fallback bảo thủ: với tiếng Việt, 1 token thường không vượt quá vài ký tự.
            # Cắt theo ký tự để tránh gửi văn bản cực dài khi tokenizer local không sẵn sàng.
            return text[: self.max_input_tokens * 2]

        tokens = self._encoding.encode(text)
        if len(tokens) <= self.max_input_tokens:
            return text
        return self._encoding.decode(tokens[: self.max_input_tokens]).rstrip()


@lru_cache(maxsize=1)
def get_embeddings_client() -> EmbeddingsClient:
    """Dùng chung một embedding client cho build index và query retrieval."""

    return EmbeddingsClient()
