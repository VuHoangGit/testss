"""Bảng `users` — danh tính lấy từ Google HOẶC đăng ký email/mật khẩu.

Khóa danh tính Google là `google_sub` (UNIQUE, nullable — tài khoản mật khẩu
không có). Email KHÔNG unique vì Google cho phép đổi email trên cùng account —
upsert theo google_sub chỉ UPDATE email (EC-27). Tài khoản mật khẩu có
`password_hash` (PBKDF2, xem app.core.passwords); chưa gắn mật khẩu thì NULL.
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
    google_sub: Mapped[str | None] = mapped_column(String(255), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(320), index=True)
    password_hash: Mapped[str | None] = mapped_column(String(255), default=None)
    name: Mapped[str | None] = mapped_column(String(255), default=None)
    avatar_url: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
