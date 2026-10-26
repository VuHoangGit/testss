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
    avatar_url: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
