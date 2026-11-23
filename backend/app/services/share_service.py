"""Nghiệp vụ chia sẻ link công khai + bình luận ghim vị trí (SRS).

Nguyên tắc bảo mật:
- Token raw chỉ trả 1 lần lúc tạo; DB lưu SHA-256 hash.
- Mọi truy cập public suy từ token hash — client không bao giờ gửi id nội bộ.
- Token sai/thu hồi/hết hạn → cùng 1 lỗi 404 chung chung (chống dò).
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DatabaseSession

from app.core.config import get_settings
from app.models.document import Document
from app.models.document_share import (
    MAX_ACTIVE_SHARES_PER_DOCUMENT,
    DocumentShare,
)
from app.models.share_comment import MAX_COMMENTS_PER_SHARE, ShareComment
from app.models.user import User
from app.schemas.shares import ALLOWED_EXPIRY_HOURS

# Thông điệp 404 chung chung cho mọi lý do link chết (FR-2.3)
LINK_NOT_FOUND = "Link không tồn tại hoặc đã hết hạn"


def hash_token(token: str) -> str:
    """SHA-256 hex của token — dạng lưu trong DB."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def build_share_url(token: str) -> str:
    """URL đầy đủ gửi cho người nhận: {PUBLIC_WEB_BASE_URL}/?share={token}."""
    base = get_settings().public_web_base_url.rstrip("/")
    return f"{base}/?share={token}"


def create_share(
    db: DatabaseSession,
    *,
    document: Document,
    permission: str,
    expires_in_hours: int | None,
) -> tuple[DocumentShare, str]:
    """Tạo link mới cho tài liệu. Trả (share, raw_token) — token chỉ hiện lần này.

    Sinh token trước, kiểm tra trùng hash (về mặt xác suất ~0 nhưng vẫn chặn),
    giới hạn 10 link đang hoạt động (FR-1.6).
    """
    if expires_in_hours is not None and expires_in_hours not in (
        h for h in ALLOWED_EXPIRY_HOURS if h is not None
    ):
        raise HTTPException(
            status_code=400,
            detail="Thời hạn không hợp lệ (chọn 1, 7, 30 ngày hoặc không hết hạn)",
        )

    active_total = db.scalar(
        select(func.count())
        .select_from(DocumentShare)
        .where(
            DocumentShare.document_id == document.id,
            DocumentShare.is_active.is_(True),
        )
    )
    if int(active_total or 0) >= MAX_ACTIVE_SHARES_PER_DOCUMENT:
        raise HTTPException(
            status_code=400,
            detail="Đã đạt giới hạn 10 link đang hoạt động",
        )

    for _ in range(5):
        token = secrets.token_urlsafe(24)  # ~192 bit entropy
        token_hash = hash_token(token)
        exists = db.scalar(
            select(DocumentShare.id).where(DocumentShare.token_hash == token_hash)
        )
        if exists is None:
            break
    else:  # pragma: no cover — xác suất trùng ~0
        raise HTTPException(status_code=500, detail="Không tạo được link, thử lại")

    expires_at = (
        datetime.now(UTC) + timedelta(hours=expires_in_hours)
        if expires_in_hours is not None
        else None
    )
    share = DocumentShare(
        document_id=document.id,
        token_hash=token_hash,
        permission=permission,
        expires_at=expires_at,
    )
    db.add(share)
    db.commit()
    db.refresh(share)
    return share, token


def list_shares(db: DatabaseSession, document: Document) -> list[DocumentShare]:
    """Mọi link của tài liệu (gồm đã thu hồi/hết hạn — FR-1.4)."""
    return list(
        db.scalars(
            select(DocumentShare)
            .where(DocumentShare.document_id == document.id)
            .order_by(DocumentShare.created_at.desc())
        )
    )


def revoke_share(db: DatabaseSession, document: Document, share_id) -> None:
    """Thu hồi link (is_active=false). Sai id → 404 như không tồn tại (FR-1.7)."""
    share = db.get(DocumentShare, share_id)
    if share is None or share.document_id != document.id:
        raise HTTPException(status_code=404, detail="Link không tồn tại")
    share.is_active = False
    db.commit()


def resolve_share_or_404(
    db: DatabaseSession, token: str
) -> tuple[DocumentShare, Document]:
    """Tìm link theo token; sai/thu hồi/hết hạn → 404 chung chung (FR-2.3/2.4)."""
    share = db.scalar(
        select(DocumentShare).where(DocumentShare.token_hash == hash_token(token))
    )
    if share is None or not share.is_active:
        raise HTTPException(status_code=404, detail=LINK_NOT_FOUND)
    if share.expires_at is not None and share.expires_at <= datetime.now(UTC):
        raise HTTPException(status_code=404, detail=LINK_NOT_FOUND)
    document = db.get(Document, share.document_id)
    if document is None:
        # DB cascade phải xóa share khi xóa document — phòng hàng mồ côi
        raise HTTPException(status_code=404, detail=LINK_NOT_FOUND)
    return share, document


def owner_display_name(owner: User) -> str:
    """Tên hiển thị trên banner cho người nhận."""
    return (owner.name or "").strip() or owner.email.split("@", 1)[0]


def sanitize_filename(name: str) -> str:
    """Tên file an toàn cho header Content-Disposition (không \\r \\n / \\)."""
    cleaned = "".join(
        ch for ch in name if ch.isprintable() and ch not in "\r\n\"/\\"
    ).strip()
    return cleaned or "tai-lieu"


def list_comments(
    db: DatabaseSession, share: DocumentShare
) -> list[ShareComment]:
    """Toàn bộ comment của link, sort (page_number, created_at) — FR-5."""
    return list(
        db.scalars(
            select(ShareComment)
            .where(ShareComment.share_id == share.id)
            .order_by(ShareComment.page_number, ShareComment.created_at)
        )
    )


def add_comment(
    db: DatabaseSession, share: DocumentShare, payload
) -> ShareComment:
    """Thêm comment từ người nhận. Link view → 403 (FR-4.5); đầy → 400 (FR-4.6)."""
    if share.permission != "comment":
        raise HTTPException(status_code=403, detail="Link này chỉ cho phép xem")

    total = db.scalar(
        select(func.count())
        .select_from(ShareComment)
        .where(ShareComment.share_id == share.id)
    )
    if int(total or 0) >= MAX_COMMENTS_PER_SHARE:
        raise HTTPException(status_code=400, detail="Chủ đề đã đầy")

    if payload.parent_id is not None:
        parent = db.get(ShareComment, payload.parent_id)
        # Reply đúng 1 cấp: parent phải thuộc share và là comment gốc (FR-4.4)
        if parent is None or parent.share_id != share.id or parent.parent_id is not None:
            raise HTTPException(status_code=400, detail="Không thể trả lời bình luận này")

    author = payload.author_name.strip()[:80]
    comment = ShareComment(
        share_id=share.id,
        parent_id=payload.parent_id,
        page_number=payload.page_number,
        norm_x=payload.norm_x,
        norm_y=payload.norm_y,
        is_pinned=payload.is_pinned,
        author_name=author or "Khách",
        body=payload.body,
    )
    db.add(comment)
    db.commit()
    db.refresh(comment)
    return comment


def list_all_comments_for_owner(
    db: DatabaseSession, document: Document
) -> list[ShareComment]:
    """Mọi comment của mọi link thuộc tài liệu (cho chủ tài liệu, FR-6.5)."""
    return list(
        db.scalars(
            select(ShareComment)
            .join(DocumentShare, ShareComment.share_id == DocumentShare.id)
            .where(DocumentShare.document_id == document.id)
            .order_by(ShareComment.created_at.desc())
        )
    )


def delete_comment_as_owner(
    db: DatabaseSession, document: Document, comment_id
) -> None:
    """Chủ tài liệu xóa comment bất kỳ; sai id → 404 (FR-4.7)."""
    comment = db.get(ShareComment, comment_id)
    if comment is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy bình luận")
    share = db.get(DocumentShare, comment.share_id)
    if share is None or share.document_id != document.id:
        raise HTTPException(status_code=404, detail="Không tìm thấy bình luận")
    # Xóa reply con TƯỜNG MINH: SQLite mặc định không bật FK pragma nên không
    # trông cậy ON DELETE CASCADE ở DB (reply chỉ 1 cấp nên 1 query là đủ).
    replies = list(
        db.scalars(
            select(ShareComment).where(ShareComment.parent_id == comment.id)
        )
    )
    for reply in replies:
        db.delete(reply)
    db.delete(comment)
    db.commit()
