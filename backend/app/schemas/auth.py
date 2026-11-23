"""Pydantic schema cho luồng xác thực: /api/v1/auth/me.

Đăng nhập/đăng ký/logout nằm hoàn toàn phía Supabase Auth — client không còn
gọi các endpoint token; backend chỉ nhận Bearer token Supabase trên mọi API.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    name: str | None = None
    avatar_url: str | None = None
    # None = chưa tự đặt tên → client hiện màn đặt tên trước khi vào app chính
    name_chosen_at: datetime | None = None


class UserNameIn(BaseModel):
    """Tên hiển thị người dùng tự nhập ở màn đặt tên."""

    name: str = Field(min_length=1, max_length=255)

    @field_validator("name")
    @classmethod
    def _strip(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Name must not be blank")
        return stripped
