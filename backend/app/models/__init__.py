"""Đăng ký toàn bộ model để Alembic/test thấy được metadata."""

from app.models.conversation import AiConversation
from app.models.document import Document
from app.models.document_share import DocumentShare
from app.models.document_version import DocumentVersion
from app.models.folder import Folder
from app.models.message import AiMessage
from app.models.payment import PaymentOrder, PricingPackage
from app.models.permission import Permission
from app.models.share_comment import ShareComment
from app.models.user import User

__all__ = [
    "User",
    "Folder",
    "Document",
    "DocumentVersion",
    "DocumentShare",
    "ShareComment",
    "Permission",
    "AiConversation",
    "AiMessage",
    "PricingPackage",
    "PaymentOrder",
]
