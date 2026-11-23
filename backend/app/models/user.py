"""Bảng `users` — profile local, danh tính do Supabase Auth quản lý.

Khóa khớp là `supabase_id` (claim `sub` trong access token Supabase, UNIQUE,
nullable). Email KHÔNG unique: đăng nhập Supabase lần đầu khớp user cũ theo
email để giữ lại documents/folders. Cột `google_sub`/`password_hash` còn trong
DB lịch sử nhưng không còn dùng — auth chuyển hết sang Supabase.
"""

import uuid
from datetime import datetime

from sqlalchemy import String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UTCDateTime


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    # UNIQUE trên cột nullable: nhiều NULL hợp lệ (PG + SQLite) — đúng ý
    supabase_id: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(320), index=True)
    name: Mapped[str | None] = mapped_column(String(255), default=None)
    # NULL = người dùng chưa TỰ đặt tên hiển thị → app hiện màn đặt tên ngay
    # sau lần đăng nhập đầu tiên (Google/email đều vậy). Có giá trị = đã đặt
    # nên không hỏi lại, và tên trong token Google không được ghi đè nữa.
    name_chosen_at: Mapped[datetime | None] = mapped_column(
        UTCDateTime, default=None
    )
    avatar_url: Mapped[str | None] = mapped_column(Text, default=None)
    # Credit dùng tính năng AI: 300 free reset đầu tháng (kỳ "YYYY-MM" đã
    # cấp gần nhất nằm ở credit_period), credit nạp mua cộng dồn không hết hạn.
    credit_free: Mapped[int] = mapped_column(default=300)
    credit_purchased: Mapped[int] = mapped_column(default=0)
    credit_period: Mapped[str] = mapped_column(String(7), default="")
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
