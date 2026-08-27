"""Hash mật khẩu (argon2) và phát hành/verify JWT."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from jose import JWTError, jwt
from passlib.context import CryptContext

from src.config import get_settings

# argon2id: hàm hash mật khẩu được khuyến nghị hiện nay (OWASP), chống tấn công
# song song bằng GPU tốt hơn bcrypt.
_pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

TokenType = Literal["access", "refresh"]


class TokenError(Exception):
    """Token thiếu, sai định dạng, sai loại hoặc đã hết hạn."""


def hash_password(password: str) -> str:
    return _pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _pwd_context.verify(password, password_hash)
    except Exception:
        # Hash rác trong DB không được làm sập luồng login.
        return False


def _create_token(subject: str, token_type: TokenType, expires_delta: timedelta) -> str:
    settings = get_settings().auth
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": subject,
        "type": token_type,
        "iat": int(now.timestamp()),
        "exp": int((now + expires_delta).timestamp()),
        # jti giúp truy vết token trong audit log.
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def create_access_token(user_id: uuid.UUID | str) -> str:
    settings = get_settings().auth
    return _create_token(str(user_id), "access", timedelta(minutes=settings.access_token_minutes))


def create_refresh_token(user_id: uuid.UUID | str) -> str:
    settings = get_settings().auth
    return _create_token(str(user_id), "refresh", timedelta(days=settings.refresh_token_days))


def decode_token(token: str, expected_type: TokenType) -> uuid.UUID:
    """Verify token và trả về user id.

    Kiểm tra cả ``type`` để refresh token không dùng được như access token.
    """

    settings = get_settings().auth
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    except JWTError as exc:
        raise TokenError("Token không hợp lệ hoặc đã hết hạn") from exc

    if payload.get("type") != expected_type:
        raise TokenError(f"Cần token loại '{expected_type}'")

    subject = payload.get("sub")
    if not subject:
        raise TokenError("Token thiếu subject")
    try:
        return uuid.UUID(subject)
    except ValueError as exc:
        raise TokenError("Subject trong token không phải UUID") from exc


def access_token_expires_in() -> int:
    """Số giây còn hiệu lực của access token, trả về cho client."""

    return get_settings().auth.access_token_minutes * 60
