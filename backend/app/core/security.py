"""Sinh/xác minh JWT access token, sinh và hash refresh token.

- Access token: JWT HS256, claim `sub` (user id), `sid` (session id), thời hạn ngắn.
- Refresh token: chuỗi ngẫu nhiên 256-bit; DB CHỈ lưu SHA-256 hex, không bao giờ plaintext.
"""

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt

from app.core.config import Settings, get_settings


class AuthError(Exception):
    """Lỗi xác thực — lớp API map ra HTTP 401 kèm message tiếng Việt."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


def create_access_token(
    user_id: uuid.UUID,
    session_id: uuid.UUID,
    *,
    email: str | None = None,
    name: str | None = None,
    picture: str | None = None,
    settings: Settings | None = None,
    now: datetime | None = None,
) -> str:
    """Cấp access JWT cho 1 session. `now` chỉ dùng trong test.

    Nhúng thêm email/name/picture để client khôi phục phiên offline mà không
    cần gọi /auth/me (luồng L3 — mở app vào thẳng Shell).
    """
    s = settings or get_settings()
    now_dt = now or datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "sid": str(session_id),
        "type": "access",
        "iss": s.jwt_issuer,
        "iat": int(now_dt.timestamp()),
        "exp": int((now_dt + timedelta(minutes=s.access_token_minutes)).timestamp()),
    }
    if email is not None:
        payload["email"] = email
    if name is not None:
        payload["name"] = name
    if picture is not None:
        payload["picture"] = picture
    return jwt.encode(payload, s.jwt_secret, algorithm=s.jwt_algorithm)


def decode_access_token(token: str, *, settings: Settings | None = None) -> dict[str, Any]:
    """Decode + verify chữ ký/issuer/hạn. Sai bất kỳ → AuthError (EC-34)."""
    s = settings or get_settings()
    try:
        payload = jwt.decode(
            token,
            s.jwt_secret,
            algorithms=[s.jwt_algorithm],
            issuer=s.jwt_issuer,
        )
    except jwt.PyJWTError as exc:
        raise AuthError("Token không hợp lệ hoặc đã hết hạn") from exc
    if payload.get("type") != "access":
        raise AuthError("Loại token không hợp lệ")
    if not payload.get("sub") or not payload.get("sid"):
        raise AuthError("Token thiếu thông tin phiên")
    return payload


def generate_refresh_token() -> str:
    """Refresh token 256-bit, chỉ trả cho client đúng 1 lần lúc login/refresh."""
    return secrets.token_urlsafe(32)


def hash_refresh_token(token: str) -> str:
    """SHA-256 hex — giá trị duy nhất được phép ghi vào DB."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
