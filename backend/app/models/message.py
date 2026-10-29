"""Bảng `ai_messages` — từng tin nhắn trong hội thoại chat AI.

`role` là chuỗi "user" | "assistant" (không dùng Enum cột — SQLite và script
migrate viết tay đều đơn giản hơn, giá trị do API kiểm soát).
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UTCDateTime
from app.models.conversation import AiConversation


class AiMessage(Base):
    __tablename__ = "ai_messages"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ai_conversations.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # Timestamp sinh phía client (microsecond) — CURRENT_TIMESTAMP của SQLite
    # chỉ chính xác tới giây nên không dùng làm thứ tự tin nhắn được
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime,
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
        nullable=False,
    )

    conversation: Mapped["AiConversation"] = relationship(back_populates="messages")
