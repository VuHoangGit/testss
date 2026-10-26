"""Nghiệp vụ xác thực: khớp danh tính Supabase với user local.

Phiên (access/refresh token) do Supabase quản lý — backend không còn bảng
session. Việc duy nhất ở đây là resolve user: tìm theo `supabase_id`, chưa có
thì khớp theo email để GIỮ LẠI documents/folders của user cũ, cuối cùng mới
tạo user mới.
"""

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import AuthError
from app.models.user import User

logger = logging.getLogger(__name__)


def resolve_supabase_user(
    db: Session,
    sub: str,
    *,
    email: str | None,
    name: str | None,
    avatar_url: str | None,
) -> User:
    """Từ claim JWT (`sub`, `email` đã verified) → user local.

    Thứ tự:
    1. Đã từng đăng nhập → tìm theo `supabase_id`, cập nhật profile nếu đổi.
    2. User cũ khớp email (tài khoản trước thời Supabase) → gán `supabase_id`
       cho row cũ, giữ nguyên id → documents/folders cũ vẫn thuộc user này.
       Nhiều row trùng email: lấy row tạo sau cùng (dữ liệu thật hiếm gặp),
       log warning để administer dò lại.
    3. Hoàn toàn mới → INSERT user mới.

    `email=None` (chưa xác thực / token không có email) chỉ chấp nhận khi `sub`
    đã từng đăng nhập — nhánh 2/3 cần email hợp lệ.
    """
    user = db.scalar(select(User).where(User.supabase_id == sub))
    if user is not None:
        if name and name != user.name:
            user.name = name
        if avatar_url and avatar_url != user.avatar_url:
            user.avatar_url = avatar_url
        db.flush()
        return user

    if not email:
        raise AuthError("Chưa xác thực email — hãy xác nhận email trong Supabase rồi đăng nhập lại")

    normalized = email.strip().lower()
    candidates = list(db.scalars(select(User).where(User.email == normalized)))
    if candidates:
        chosen = max(candidates, key=lambda u: u.created_at)
        if len(candidates) > 1:
            logger.warning(
                "Email %s trung lap %d row users — chon row id=%s (moi nhat)",
                normalized,
                len(candidates),
                chosen.id,
            )
        chosen.supabase_id = sub
        # Chỉ bổ sung thông tin còn thiếu — không đè dữ liệu user cũ đã chỉnh
        if name and not chosen.name:
            chosen.name = name
        if avatar_url and not chosen.avatar_url:
            chosen.avatar_url = avatar_url
        db.flush()
        return chosen

    user = User(supabase_id=sub, email=normalized, name=name, avatar_url=avatar_url)
    db.add(user)
    db.flush()
    return user
