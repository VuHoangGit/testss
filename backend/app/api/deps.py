"""Dependency xác thực: Bearer token Supabase → user local."""

from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session as DatabaseSession

from app.core.config import get_settings
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
        raise AuthError("Chưa đăng nhập")
    payload = verify_supabase_token(credentials.credentials)

    # Giữ cơ chế lọc domain email nếu cấu hình (rỗng = mở cho mọi account)
    domains = get_settings().allowed_email_domain_list
    email = payload.get("email")
    if domains and (
        not isinstance(email, str) or email.rsplit("@", 1)[-1].lower() not in domains
    ):
        raise AuthError("Email không thuộc domain được phép")

    # Profile (tên/ảnh) nằm trong user_metadata — Google provider điền sẵn
    raw_metadata = payload.get("user_metadata")
    metadata = raw_metadata if isinstance(raw_metadata, dict) else {}
    name = metadata.get("full_name") or metadata.get("name")
    avatar = metadata.get("avatar_url") or metadata.get("picture")

    # Chỉ tin email đã verify khi khớp user cũ/tạo mới (chống chiếm email người khác)
    email_verified = payload.get("email_verified") is True
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
