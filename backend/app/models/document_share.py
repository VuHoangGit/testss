"""Bảng `document_shares` — link chia sẻ công khai theo token (P1 SRS).

Người nhận link KHÔNG có tài khoản nên không thể dùng bảng `permissions`
(thiết kế cho user_id NOT NULL). Link xác định bằng token: server lưu SHA-256
hash của token, raw token chỉ xuất hiện đúng 1 lần trong URL khi tạo link.
"""

import uuid
from datetime import datetime

from sqlalchemy import CHAR, ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UTCDateTime

# Số link đang hoạt động tối đa của 1 tài liệu (FR-1.6)
MAX_ACTIVE_SHARES_PER_DOCUMENT = 10


class DocumentShare(Base):
    __tablename__ = "document_shares"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    # SHA-256 hex (64 ký tự) của token — không bao giờ lưu token thô
    token_hash: Mapped[str] = mapped_column(
        CHAR(64), unique=True, index=True, nullable=False
    )
    # 'view' | 'comment' (P2)
    permission: Mapped[str] = mapped_column(String(10), nullable=False, default="view")
    # NULL = không hết hạn; hết hạn tính theo giờ server lúc nhận request
    expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)
    # Thu hồi = false; link thu hồi trả 404 như link không tồn tại
    is_active: Mapped[bool] = mapped_column(
        nullable=False, default=True, server_default="1"
    )
    view_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, server_default=func.now(), nullable=False
    )

    # Xóa tài liệu → xóa hết link + comment của link đó
    document = relationship("Document", back_populates="shares")
    comments = relationship(
        "ShareComment", back_populates="share", cascade="all, delete-orphan"
    )


Index("ix_shares_document", DocumentShare.document_id)
