"""Bảng `sessions` — 1 dòng = 1 lần đăng nhập trên 1 thiết bị.

`refresh_token_hash` là SHA-256 hex của refresh token (UNIQUE) — tuyệt đối không
lưu plaintext. `id` chính là claim `sid` trong access JWT; access token stateless
nên thu hồi phiên luôn đi qua bảng này.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UTCDateTime


class UserSession(Base):
    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    refresh_token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    device_info: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime, index=True, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)
    last_used_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
