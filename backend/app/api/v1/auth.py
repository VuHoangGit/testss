"""Endpoints xác thực: /auth/google, /auth/refresh, /auth/logout, /auth/me.

AuthError phát từ bất kỳ lớp nào sẽ được exception handler ở main.py map ra 401.
"""

from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession
from app.core.google import GoogleIdentity, verify_google_id_token
from app.schemas.auth import (
    GoogleLoginRequest,
    RefreshRequest,
    RefreshResponse,
    TokenResponse,
    UserOut,
)
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/google", response_model=TokenResponse)
def login_with_google(body: GoogleLoginRequest, db: DbSession) -> TokenResponse:
    """Luồng L2: client gửi id_token từ Google SDK, backend verify + cấp cặp token."""
    identity: GoogleIdentity = verify_google_id_token(body.id_token)
    user, session, refresh_token = auth_service.login_with_google(db, identity, body.device_info)
    access_token, expires_in = auth_service.issue_tokens(user, session)
    db.commit()
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=expires_in,
        user=UserOut.model_validate(user),
    )


@router.post("/refresh", response_model=RefreshResponse)
def refresh(body: RefreshRequest, db: DbSession) -> RefreshResponse:
    """Luồng L3: đổi refresh token lấy cặp token mới (rotation — token cũ chết ngay)."""
    user, session, new_refresh_token = auth_service.rotate_session(db, body.refresh_token)
    access_token, expires_in = auth_service.issue_tokens(user, session)
    db.commit()
    return RefreshResponse(
        access_token=access_token,
        refresh_token=new_refresh_token,
        expires_in=expires_in,
    )


@router.post("/logout")
def logout(db: DbSession, current: CurrentUser) -> dict[str, str]:
    """Luồng L4: thu hồi session hiện tại. Idempotent — gọi lại không lỗi."""
    session, _ = current
    auth_service.logout_session(db, session.id)
    db.commit()
    return {"detail": "Đã đăng xuất"}


@router.get("/me", response_model=UserOut)
def me(current: CurrentUser) -> UserOut:
    """Thông tin user của phiên hiện tại (Shell dùng hiển thị tên/avatar)."""
    _, user = current
    return UserOut.model_validate(user)
