"""Pydantic schema cho luồng xác thực (hiện chỉ còn /api/v1/auth/me).

Đăng nhập/đăng ký/logout nằm hoàn toàn phía Supabase Auth — client không còn
gọi các endpoint token; backend chỉ nhận Bearer token Supabase trên mọi API.
"""

import uuid

from pydantic import BaseModel, ConfigDict


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    name: str | None = None
    avatar_url: str | None = None
