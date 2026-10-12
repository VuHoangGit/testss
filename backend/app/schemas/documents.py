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
    created_at: datetime


class MergeRequest(BaseModel):
    document_ids: list[uuid.UUID] = Field(min_length=2)
    name: str = Field(min_length=1, max_length=255)


class SplitRequest(BaseModel):
    ranges: str = Field(min_length=1, max_length=255, examples=["1-3,5"])


class ProtectRequest(BaseModel):
    password: str = Field(min_length=1, max_length=128)


class UnprotectRequest(ProtectRequest):
    pass
