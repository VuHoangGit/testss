"""Endpoints xác thực: /auth/me.

Đăng nhập Google/email do Supabase Auth xử lý phía client; backend chỉ verify
access token Supabase (xem app.api.deps) và trả profile từ bảng users local.
AuthError phát từ bất kỳ lớp nào sẽ được exception handler ở main.py map ra 401.
"""

from datetime import UTC, datetime

from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession
from app.schemas.auth import UserNameIn, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/me", response_model=UserOut)
def me(current: CurrentUser) -> UserOut:
    """Thông tin user của phiên hiện tại (Shell dùng hiển thị tên/avatar)."""
    return UserOut.model_validate(current)


@router.patch("/me", response_model=UserOut)
def update_me(payload: UserNameIn, current: CurrentUser, db: DbSession) -> UserOut:
    """Đặt tên hiển thị (màn đặt tên ngay sau lần đăng nhập đầu tiên).

    Đánh dấu `name_chosen_at` để app không hỏi lại, và để tên Google trong
    token không ghi đè lựa chọn của người dùng ở các lần đăng nhập sau.
    """
    current.name = payload.name
    current.name_chosen_at = datetime.now(UTC)
    db.commit()
    return UserOut.model_validate(current)
