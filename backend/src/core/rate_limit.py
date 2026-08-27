"""Rate limit cho các endpoint tốn quota LLM.

Dùng slowapi với bộ đếm in-memory: đủ cho một instance backend. Nếu scale nhiều
worker thì trỏ ``storage_uri`` sang Redis.
"""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from src.config import Settings, get_settings


def _identify(request: Request) -> str:
    """Đếm quota theo user đã đăng nhập, fallback về IP cho request nặc danh.

    Dùng user id giúp nhiều người sau cùng một NAT không ăn chung hạn mức.
    """

    user = getattr(request.state, "user", None)
    if user is not None:
        return f"user:{user.id}"
    auth = request.headers.get("authorization", "")
    if auth.startswith("Bearer "):
        return f"token:{auth[7:][:32]}"
    return f"ip:{get_remote_address(request)}"


limiter = Limiter(key_func=_identify, enabled=True)


def _chat_limit_value() -> str:
    """Chuỗi giới hạn cho endpoint chat, đọc từ config.

    Truyền dạng callable để slowapi đọc lại config mỗi request, nhờ vậy đổi
    ``rate_limit.chat_per_minute`` không cần sửa code decorator.
    """

    return f"{get_settings().rate_limit.chat_per_minute}/minute"


def _upload_limit_value() -> str:
    return f"{get_settings().rate_limit.upload_per_hour}/hour"


# Decorator dùng trực tiếp trên route handler. Handler bắt buộc có tham số
# ``request: Request`` để slowapi lấy được key.
chat_rate_limit = limiter.limit(_chat_limit_value)
upload_rate_limit = limiter.limit(_upload_limit_value)


async def rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """Trả 429 kèm thông báo tiếng Việt thay vì lỗi mặc định."""

    return JSONResponse(
        status_code=429,
        content={
            "detail": (
                "Bạn đã gửi quá nhiều yêu cầu trong thời gian ngắn. "
                "Vui lòng đợi một phút rồi thử lại."
            ),
            "limit": str(exc.detail),
        },
    )


def install_rate_limiter(app: FastAPI, settings: Settings) -> None:
    """Gắn limiter vào app; tôn trọng cờ ``rate_limit.enabled``."""

    limiter.enabled = settings.rate_limit.enabled
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_handler)
