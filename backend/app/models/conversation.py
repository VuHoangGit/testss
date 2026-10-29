"""Bảng `ai_conversations` — hội thoại chat với AI, gắn theo tài liệu.

Mỗi tài liệu có thể có nhiều hội thoại; UI hiện dùng 1 hội thoại/tài liệu (mở
chat → load hội thoại mới nhất). Xóa tài liệu (hoặc user) → cascade xóa hội
thoại kèm toàn bộ tin nhắn.
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UTCDateTime
from app.models.document import Document

if TYPE_CHECKING:
    from app.models.message import AiMessage


class AiConversation(Base):
    __tablename__ = "ai_conversations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True, default=None
    )
    # Câu hỏi đầu tiên làm tên hội thoại (rút ngắn còn 255 ký tự)
    title: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    messages: Mapped[list["AiMessage"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="AiMessage.created_at",
    )
    document: Mapped[Document] = relationship(back_populates="ai_conversations")
