"""Pydantic schema cho chia sẻ link công khai + bình luận ghim (SRS)."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

# Thời hạn link cho phép (giờ); None = không hết hạn (FR-1.2)
ALLOWED_EXPIRY_HOURS = (24, 24 * 7, 24 * 30, None)


class ShareCreate(BaseModel):
    """Body tạo link chia sẻ."""

    # 'comment' cho phép người nhận ghim/trả lời bình luận (P2).
    permission: str = Field(default="view", pattern="^(view|comment)$")
    # None = không hết hạn; giá trị khác phải thuộc ALLOWED_EXPIRY_HOURS
    expires_in_hours: int | None = None


class ShareOut(BaseModel):
    """Link chia sẻ cho CHỦ tài liệu (nhóm đăng nhập).

    `share_url` chỉ có ở response tạo mới (raw token không lưu — hiện lại
    không thể nào). Danh sách link trả share_url rỗng.
    """

    id: uuid.UUID
    permission: str
    expires_at: datetime | None = None
    is_active: bool
    view_count: int
    share_url: str = ""
    created_at: datetime


class PublicShareMeta(BaseModel):
    """Metadata trả cho người nhận (KHÔNG có id nội bộ nào — FR-2.1)."""

    file_name: str
    mime_type: str
    size_bytes: int
    page_count: int | None = None
    permission: str
    expires_at: datetime | None = None
    owner_name: str


class ShareCommentCreate(BaseModel):
    """Body thêm comment từ người nhận link."""

    page_number: int = Field(ge=1)
    norm_x: float = Field(ge=0.0, le=1.0)
    norm_y: float = Field(ge=0.0, le=1.0)
    # False = thread chung (ảnh/text hoặc nút Bình luận), không vẽ pin PDF.
    is_pinned: bool = True
    author_name: str = Field(default="", max_length=80)
    body: str = Field(min_length=1, max_length=2000)
    # Reply 1 cấp: phải là comment gốc (không có parent) của cùng share
    parent_id: uuid.UUID | None = None


class ShareCommentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    parent_id: uuid.UUID | None = None
    page_number: int
    norm_x: float
    norm_y: float
    is_pinned: bool = True
    author_name: str
    body: str
    created_at: datetime


class OwnerShareCommentOut(ShareCommentOut):
    """Comment cho chủ tài liệu — kèm share_id (nhóm đăng nhập)."""

    share_id: uuid.UUID
