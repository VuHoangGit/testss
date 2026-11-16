"""Pydantic schema cho folders/documents (Sprint 2)."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class FolderCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class FolderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    document_count: int = 0


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    folder_id: uuid.UUID | None = None
    original_name: str
    mime_type: str
    size_bytes: int
    page_count: int | None = None
    is_favorite: bool = False
    last_opened_at: datetime | None = None
    created_at: datetime


class FavoriteRequest(BaseModel):
    favorite: bool


class StorageUsageOut(BaseModel):
    """Dung lượng tài liệu đã dùng so với hạn mức (`quota_bytes=None` = không giới hạn)."""

    used_bytes: int
    quota_bytes: int | None = None


class MergeRequest(BaseModel):
    document_ids: list[uuid.UUID] = Field(min_length=2)
    name: str = Field(min_length=1, max_length=255)


class SplitRequest(BaseModel):
    ranges: str = Field(min_length=1, max_length=255, examples=["1-3,5"])


class ProtectRequest(BaseModel):
    password: str = Field(min_length=1, max_length=128)


class UnprotectRequest(ProtectRequest):
    pass


class DocumentVersionOut(BaseModel):
    """Một bản cũ trong lịch sử phiên bản của tài liệu."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    document_id: uuid.UUID
    version_number: int
    size_bytes: int
    page_count: int | None = None
    label: str
    created_at: datetime


class VersionDiffRequest(BaseModel):
    """Chọn 2 phiên bản để so sánh: một bản cũ + bản hiện tại hoặc hai bản cũ."""

    old_version_id: uuid.UUID
    new_version_id: uuid.UUID | None = None  # None = so với bản hiện tại


class VersionDiffResult(BaseModel):
    diff: list[str]
    added: int
    removed: int
    ai_summary: str | None = None
