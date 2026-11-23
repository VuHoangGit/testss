"""Bảng `share_comments` — bình luận ghim vị trí thuộc về share link (P2 SRS).

Comment thuộc về link (không phải document): vào bằng link nào thì thấy/thêm
comment của link đó. Vị trí ghim theo tọa độ chuẩn hóa trang PDF để độc lập
với zoom/màn hình.
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UTCDateTime

# Số comment tối đa của 1 share link (FR-4.6)
MAX_COMMENTS_PER_SHARE = 500


class ShareComment(Base):
    __tablename__ = "share_comments"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    share_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("document_shares.id", ondelete="CASCADE"), nullable=False
    )
    # Reply 1 cấp: parent phải là comment gốc của cùng share (không lồng sâu)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("share_comments.id", ondelete="CASCADE"), default=None
    )
    # 1-based, khớp số trang hiển thị trong viewer
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    # Tọa độ chuẩn hóa [0,1] theo kích thước trang PDF
    norm_x: Mapped[float] = mapped_column(Float, nullable=False)
    norm_y: Mapped[float] = mapped_column(Float, nullable=False)
    # Thread chung vẫn có tọa độ trung tính nhưng không vẽ pin (FR-4.8).
    is_pinned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Tên người nhận tự nhập; bỏ trống → "Khách" (không tài khoản, không xác thực)
    author_name: Mapped[str] = mapped_column(String(80), nullable=False, default="Khách")
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, server_default=func.now(), nullable=False
    )

    share = relationship("DocumentShare", back_populates="comments")
