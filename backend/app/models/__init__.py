"""Đăng ký toàn bộ model để Alembic/test thấy được metadata."""

from app.models.conversation import AiConversation
from app.models.document import Document
from app.models.folder import Folder
from app.models.message import AiMessage
from app.models.permission import Permission
from app.models.user import User

__all__ = [
    "User",
    "Folder",
    "Document",
    "Permission",
    "AiConversation",
    "AiMessage",
]
