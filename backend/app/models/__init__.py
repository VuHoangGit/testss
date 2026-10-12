"""Đăng ký toàn bộ model để Alembic/test thấy được metadata."""

from app.models.session import UserSession
from app.models.user import User

__all__ = ["User", "UserSession"]
