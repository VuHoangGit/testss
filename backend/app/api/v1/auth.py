"""Endpoints xác thực: /auth/me.

Đăng nhập Google/email do Supabase Auth xử lý phía client; backend chỉ verify
access token Supabase (xem app.api.deps) và trả profile từ bảng users local.
AuthError phát từ bất kỳ lớp nào sẽ được exception handler ở main.py map ra 401.
"""

from fastapi import APIRouter

from app.api.deps import CurrentUser
from app.schemas.auth import UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/me", response_model=UserOut)
def me(current: CurrentUser) -> UserOut:
    """Thông tin user của phiên hiện tại (Shell dùng hiển thị tên/avatar)."""
    return UserOut.model_validate(current)
