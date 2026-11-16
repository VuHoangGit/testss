"""Dependency xác thực: Bearer token Supabase → user local + giới hạn tần suất."""

from typing import Annotated

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session as DatabaseSession

from app.core.config import get_settings
from app.core.ratelimit import get_limiter
from app.core.security import AuthError, verify_supabase_token
from app.db.session import get_db
from app.models.user import User
from app.services import auth_service

# auto_error=False để tự raise AuthError (thống nhất message tiếng Việt)
_bearer_scheme = HTTPBearer(auto_error=False)

# Alias dùng chung cho các endpoint
DbSession = Annotated[DatabaseSession, Depends(get_db)]


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
    db: DbSession,
) -> User:
    if credentials is None:
        raise AuthError("Not signed in")
    payload = verify_supabase_token(credentials.credentials)

    # Giữ cơ chế lọc domain email nếu cấu hình (rỗng = mở cho mọi account)
    domains = get_settings().allowed_email_domain_list
    email = payload.get("email")
    if domains and (
        not isinstance(email, str) or email.rsplit("@", 1)[-1].lower() not in domains
    ):
        raise AuthError("Email is not in an allowed domain")

    # Profile (tên/ảnh) nằm trong user_metadata — Google provider điền sẵn
    raw_metadata = payload.get("user_metadata")
    metadata = raw_metadata if isinstance(raw_metadata, dict) else {}
    name = metadata.get("full_name") or metadata.get("name")
    avatar = metadata.get("avatar_url") or metadata.get("picture")

    # Chỉ tin email đã verify khi khớp user cũ/tạo mới (chống chiếm email người khác).
    # Token từ JWT Signing Keys mới của Supabase KHÔNG còn claim `email_verified`
    # (đo trên token thật) — Supabase chỉ cấp token password/OAuth cho account đã
    # xác nhận email, nên token đã verify chữ ký thì email đáng tin; chỉ chặn
    # khi claim = false tường minh.
    email_verified = payload.get("email_verified", True) is True
    user = auth_service.resolve_supabase_user(
        db,
        str(payload["sub"]),
        email=email if (email_verified and isinstance(email, str)) else None,
        name=name if isinstance(name, str) else None,
        avatar_url=avatar if isinstance(avatar, str) else None,
    )
    # Lần đầu đăng nhập có thể INSERT user mới — commit ngay để phiên lưu thật
    # (endpoint phía sau không biết về việc này nên không tự commit được).
    db.commit()
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def _enforce_rate_limit(group: str, user_id: object, max_calls: int) -> None:
    """Chặn khi user vượt hạn mức `max_calls` lượt/phút → HTTP 429 + Retry-After."""
    retry_after = get_limiter(group).hit(f"user:{user_id}", max_calls, 60.0)
    if retry_after is not None:
        raise HTTPException(
            status_code=429,
            detail="Too many requests — please slow down and try again",
            headers={"Retry-After": str(int(retry_after) + 1)},
        )


def ai_rate_limit(current: CurrentUser) -> None:
    """Giới hạn lượt gọi AI theo user (mỗi lượt là tiền thật trả nhà cung cấp AI)."""
    settings = get_settings()
    if settings.rate_limit_enabled:
        _enforce_rate_limit("ai", current.id, settings.rate_limit_ai_per_minute)


def upload_rate_limit(current: CurrentUser) -> None:
    """Giới hạn lượt upload theo user (chặn spam đầy đĩa)."""
    settings = get_settings()
    if settings.rate_limit_enabled:
        _enforce_rate_limit("upload", current.id, settings.rate_limit_upload_per_minute)


def order_rate_limit(current: CurrentUser) -> None:
    """Giới hạn lượt tạo đơn nạp theo user (chặn spam bảng payments)."""
    settings = get_settings()
    if settings.rate_limit_enabled:
        _enforce_rate_limit("orders", current.id, settings.rate_limit_orders_per_minute)
