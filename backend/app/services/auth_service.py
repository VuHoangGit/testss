"""Nghiệp vụ xác thực: upsert user theo google_sub, tạo/xoay/thu hồi session.

Refresh rotation: session cũ revoke + tạo session mới. Reuse refresh token đã
revoke → 401 nghiêm ngặt (EC-11) — client chống race bằng single-flight refresh.
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.google import GoogleIdentity
from app.core.security import (
    AuthError,
    create_access_token,
    generate_refresh_token,
    hash_refresh_token,
)
from app.models.session import UserSession
from app.models.user import User

# Giới hạn device_info để dữ liệu hiển thị không bao giờ gây lỗi 500 (EC-32)
_MAX_DEVICE_KEYS = 20
_MAX_DEVICE_KEY_LENGTH = 40
_MAX_DEVICE_VALUE_LENGTH = 300


def _sanitize_device_info(device_info: dict[str, str] | None) -> dict[str, str] | None:
    if not device_info:
        return None
    items = list(device_info.items())[:_MAX_DEVICE_KEYS]
    return {
        str(key)[:_MAX_DEVICE_KEY_LENGTH]: str(value)[:_MAX_DEVICE_VALUE_LENGTH]
        for key, value in items
    }


def upsert_user_by_google(db: Session, identity: GoogleIdentity) -> User:
    """Chưa có → INSERT; đã có → cập nhật email/name/avatar theo dữ liệu Google mới (EC-27)."""
    user = db.scalar(select(User).where(User.google_sub == identity.google_sub))
    if user is None:
        user = User(
            google_sub=identity.google_sub,
            email=identity.email,
            name=identity.name,
            avatar_url=identity.avatar_url,
        )
        db.add(user)
        db.flush()
    else:
        user.email = identity.email
        user.name = identity.name
        user.avatar_url = identity.avatar_url
        db.flush()
    return user


def create_session(
    db: Session,
    user_id: uuid.UUID,
    device_info: dict[str, str] | None = None,
    *,
    settings: Settings | None = None,
) -> tuple[UserSession, str]:
    """Tạo session + refresh token (token plain trả về client đúng 1 lần)."""
    s = settings or get_settings()
    refresh_token = generate_refresh_token()
    session = UserSession(
        user_id=user_id,
        refresh_token_hash=hash_refresh_token(refresh_token),
        device_info=_sanitize_device_info(device_info),
        expires_at=datetime.now(UTC) + timedelta(days=s.refresh_token_days),
    )
    db.add(session)
    db.flush()
    return session, refresh_token


def login_with_google(
    db: Session,
    identity: GoogleIdentity,
    device_info: dict[str, str] | None,
) -> tuple[User, UserSession, str]:
    """Luồng L2: upsert user → tạo session. Idempotent theo google_sub (EC-36)."""
    user = upsert_user_by_google(db, identity)
    session, refresh_token = create_session(db, user.id, device_info)
    return user, session, refresh_token


def rotate_session(db: Session, refresh_token: str) -> tuple[User, UserSession, str]:
    """Luồng L3: refresh + rotation.

    Hợp lệ → revoke session cũ, tạo session mới. Sai/hết hạn/reuse đã revoke → AuthError.
    """
    token_hash = hash_refresh_token(refresh_token)
    old_session = db.scalar(select(UserSession).where(UserSession.refresh_token_hash == token_hash))
    if old_session is None or old_session.revoked_at is not None:
        raise AuthError("Phiên đăng nhập không hợp lệ")

    now = datetime.now(UTC)
    if old_session.expires_at <= now:
        raise AuthError("Phiên đăng nhập đã hết hạn")

    user = db.get(User, old_session.user_id)
    if user is None:
        raise AuthError("Phiên đăng nhập không hợp lệ")

    old_session.revoked_at = now
    old_session.last_used_at = now
    new_session, new_refresh_token = create_session(db, user.id, old_session.device_info)
    return user, new_session, new_refresh_token


def logout_session(db: Session, session_id: uuid.UUID) -> None:
    """Luồng L4: thu hồi session — idempotent (EC-20), không ảnh hưởng session khác (EC-19)."""
    db.execute(
        update(UserSession)
        .where(UserSession.id == session_id, UserSession.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )


def issue_tokens(user: User, session: UserSession) -> tuple[str, int]:
    """Cặp (access JWT, expires_in giây) — JWT nhúng profile để client dùng offline."""
    settings = get_settings()
    access_token = create_access_token(
        user.id, session.id, email=user.email, name=user.name, picture=user.avatar_url
    )
    return access_token, settings.access_token_minutes * 60


def load_session_and_user(db: Session, payload: dict[str, Any]) -> tuple[UserSession, User]:
    """Từ claim JWT load session + user còn hiệu lực; đã revoke/xóa → AuthError (EC-17/18)."""
    try:
        session_id = uuid.UUID(str(payload.get("sid")))
        user_id = uuid.UUID(str(payload.get("sub")))
    except ValueError as exc:
        raise AuthError("Token không hợp lệ") from exc

    session = db.get(UserSession, session_id)
    user = db.get(User, user_id)
    if session is None or user is None or session.user_id != user_id:
        raise AuthError("Phiên đăng nhập không hợp lệ")
    if session.revoked_at is not None:
        raise AuthError("Phiên đăng nhập đã bị thu hồi")
    return session, user
