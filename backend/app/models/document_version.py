"""Bảng `document_versions` — lịch sử phiên bản của tài liệu (tính năng mới).

Khi upload bản mới của cùng một tài liệu, file hiện tại không bị ghi đè: nó
được hạ xuống làm phiên bản cũ và vẫn tải/xem/so sánh được. Mỗi bản lưu một
storage_key riêng nên restore chỉ là đổi con trỏ, không sao chép file.

Giới hạn [MAX_VERSIONS_PER_DOCUMENT] bản/tài liệu (FIFO): vượt thì bản cũ
nhất bị xóa hẳn (file + row) để quota đĩa không phình vô hạn.
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UTCDateTime

if TYPE_CHECKING:
    from app.models.document import Document

# Giữ nhiều hơn nữa thì gần như không ai đọc lại và quota đĩa phình nhanh.
MAX_VERSIONS_PER_DOCUMENT = 10


class DocumentVersion(Base):
    """Một bản cũ của tài liệu — điểm khôi phục của lịch sử phiên bản."""

    __tablename__ = "document_versions"
    __table_args__ = (
        # Một số thứ tự phiên bản chỉ xuất hiện đúng 1 lần mỗi tài liệu.
        UniqueConstraint("document_id", "version_number", name="uq_version_number"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # Số thứ tự: 1 = bản gần nhất đã bị thay thế, 2 = cũ hơn...
    version_number: Mapped[int] = mapped_column(nullable=False)
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int] = mapped_column(nullable=False)
    page_count: Mapped[int | None] = mapped_column(default=None)
    # Ghi chú do người dùng nhập khi upload bản mới (vd "sau khi khách sửa điều 4").
    label: Mapped[str] = mapped_column(default="", server_default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, server_default=func.now(), nullable=False
    )

    document: Mapped["Document"] = relationship(
        back_populates="versions",
    )
