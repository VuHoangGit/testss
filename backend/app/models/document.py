"""Bảng `documents` — metadata file đã upload; nội dung nằm ở storage (Sprint 2).

`storage_key` do server sinh (uuid + đuôi file) — không dùng tên gốc làm path
(chống path traversal, trùng tên).
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UTCDateTime

if TYPE_CHECKING:
    from app.models.conversation import AiConversation
    from app.models.document_version import DocumentVersion


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    folder_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("folders.id", ondelete="SET NULL"), index=True, default=None
    )
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_key: Mapped[str] = mapped_column(Text, unique=True, index=True, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(127), default="application/octet-stream")
    size_bytes: Mapped[int] = mapped_column(nullable=False)
    page_count: Mapped[int | None] = mapped_column(default=None)
    # Đánh dấu sao (TOOLS → Favorites); boolean nên để SQLite default "0"
    is_favorite: Mapped[bool] = mapped_column(
        nullable=False, default=False, server_default="0"
    )
    # Lần mở gần nhất (TOOLS → Recent); null = chưa từng mở
    last_opened_at: Mapped[datetime | None] = mapped_column(
        UTCDateTime, default=None
    )
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Xóa tài liệu → cascade xóa hội thoại AI + tin nhắn (ORM-level cascade nên
    # chạy được cả khi SQLite không bật FK pragma)
    ai_conversations: Mapped[list["AiConversation"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )
    # Lịch sử phiên bản (upload bản mới không mất bản cũ) — cascade xóa luôn
    # các bản cũ khi tài liệu bị xóa.
    versions: Mapped[list["DocumentVersion"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="DocumentVersion.version_number",
    )
