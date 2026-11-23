"""Endpoints tài liệu: upload (multipart), list, download, xóa + công cụ PDF
(gộp / tách trang / mật khẩu) bằng pypdf phía server (Sprint 2).
"""

import uuid
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DatabaseSession

from app.api.deps import CurrentUser, DbSession, upload_rate_limit
from app.core.config import get_settings
from app.models.document import Document
from app.models.folder import Folder
from app.models.permission import Permission
from app.schemas.documents import (
    DocumentOut,
    FavoriteRequest,
    MergeRequest,
    ProtectRequest,
    SplitRequest,
    StorageUsageOut,
    UnprotectRequest,
)
from app.schemas.shares import (
    OwnerShareCommentOut,
    ShareCreate,
    ShareOut,
)
from app.services import pdf_service, share_service, storage_service

router = APIRouter(prefix="/documents", tags=["documents"])

_PDF_MIME = "application/pdf"

# Đuôi file → MIME do SERVER quyết định. Không dùng `content_type` client khai:
# client có thể gửi text/html cho file .pdf rồi lừa trình duyệt render HTML trên
# origin của API (stored XSS). Đuôi không có trong bảng = không nhận.
_EXTENSION_MIME: dict[str, str] = {
    "pdf": "application/pdf",
    "doc": "application/msword",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xls": "application/vnd.ms-excel",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "ppt": "application/vnd.ms-powerpoint",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "txt": "text/plain",
    "md": "text/markdown",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "gif": "image/gif",
    "zip": "application/zip",
}

# Chỉ những MIME này được trả lại khi download; còn lại ép octet-stream để
# trình duyệt tải về chứ không render tại chỗ.
_SAFE_DOWNLOAD_MIMES = frozenset(_EXTENSION_MIME.values())

# Đọc upload theo chunk 1 MB: file lớn hơn hạn mức bị chặn NGAY khi vượt, không
# nạp cả file vào RAM trước rồi mới kiểm tra (một request 2 GB từng làm sập worker).
_READ_CHUNK_BYTES = 1024 * 1024


def _resolve_upload_mime(original_name: str) -> str:
    """Chọn MIME theo đuôi file; đuôi ngoài danh sách cho phép → HTTP 415."""
    extension = Path(original_name).suffix.lower().lstrip(".")
    allowed = get_settings().allowed_upload_type_list
    if extension not in allowed or extension not in _EXTENSION_MIME:
        raise HTTPException(
            status_code=415,
            detail=(
                f"Unsupported file type '{extension or 'unknown'}'. "
                f"Allowed: {', '.join(allowed)}"
            ),
        )
    return _EXTENSION_MIME[extension]


async def _read_upload_limited(file: UploadFile, max_bytes: int) -> bytes:
    """Đọc nội dung upload, dừng và trả 413 ngay khi vượt `max_bytes`."""
    declared = getattr(file, "size", None)
    if isinstance(declared, int) and declared > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds {get_settings().max_upload_mb} MB",
        )
    buffer = bytearray()
    while chunk := await file.read(_READ_CHUNK_BYTES):
        buffer.extend(chunk)
        if len(buffer) > max_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"File exceeds {get_settings().max_upload_mb} MB",
            )
    return bytes(buffer)


def _used_bytes(db: DatabaseSession, owner_id: uuid.UUID) -> int:
    """Tổng dung lượng tài liệu của user (byte)."""
    total = db.scalar(
        select(func.coalesce(func.sum(Document.size_bytes), 0)).where(
            Document.owner_id == owner_id
        )
    )
    return int(total or 0)


def _archived_version_bytes(db: DatabaseSession, owner_id: uuid.UUID) -> int:
    """Tổng dung lượng các bản cũ trong lịch sử phiên bản của user (byte)."""
    from app.models.document_version import DocumentVersion  # import local tránh vòng

    total = db.scalar(
        select(func.coalesce(func.sum(DocumentVersion.size_bytes), 0))
        .join(Document, DocumentVersion.document_id == Document.id)
        .where(Document.owner_id == owner_id)
    )
    return int(total or 0)


def _ensure_storage_quota(
    db: DatabaseSession, owner_id: uuid.UUID, incoming_bytes: int
) -> None:
    """Chặn khi upload thêm sẽ vượt quota dung lượng của user → HTTP 413.

    Tính cả các bản cũ trong lịch sử phiên bản — không cho lịch sử lách quota.
    """
    quota_mb = get_settings().user_storage_quota_mb
    if quota_mb <= 0:
        return
    quota_bytes = quota_mb * 1024 * 1024
    used = _used_bytes(db, owner_id) + _archived_version_bytes(db, owner_id)
    if used + incoming_bytes > quota_bytes:
        raise HTTPException(
            status_code=413,
            detail=(
                f"Storage quota exceeded ({used / 1024 / 1024:.1f} MB of "
                f"{quota_mb} MB used, file needs {incoming_bytes / 1024 / 1024:.1f} MB)"
            ),
        )


def _get_owned_document(db: DatabaseSession, document_id: uuid.UUID, user_id) -> Document:
    doc = db.get(Document, document_id)
    if doc is None or doc.owner_id != user_id:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


def _save_new_pdf_document(
    db: DatabaseSession,
    *,
    owner_id,
    data: bytes,
    name: str,
    folder_id: uuid.UUID | None,
) -> Document:
    key = storage_service.build_storage_key(name)
    storage_service.save_document_bytes(data, key)
    doc = Document(
        owner_id=owner_id,
        folder_id=folder_id,
        original_name=name,
        storage_key=key,
        mime_type=_PDF_MIME,
        size_bytes=len(data),
        page_count=pdf_service.pdf_page_count(data),
    )
    db.add(doc)
    db.flush()
    db.add(Permission(document_id=doc.id, user_id=owner_id, role="owner"))
    return doc


@router.get("", response_model=list[DocumentOut])
def list_documents(
    db: DbSession,
    current: CurrentUser,
    folder_id: uuid.UUID | None = None,
    search: str = "",
    favorites_only: bool = False,
    sort: str = "created",
) -> list[DocumentOut]:
    """Danh sách tài liệu của user.

    - `folder_id`: lọc theo thư mục.
    - `search`: tìm gần đúng theo tên file (LIKE, không phân biệt hoa thường).
    - `favorites_only`: chỉ file đã gắn sao (TOOLS → Favorites).
    - `sort`: `created` (mới tải lên trước) hoặc `recent` (mở gần nhất trước,
      file chưa từng mở xếp cuối — TOOLS → Recent).
    """
    user = current
    stmt = select(Document).where(Document.owner_id == user.id)
    if folder_id is not None:
        stmt = stmt.where(Document.folder_id == folder_id)
    if search.strip():
        stmt = stmt.where(Document.original_name.ilike(f"%{search.strip()}%"))
    if favorites_only:
        stmt = stmt.where(Document.is_favorite.is_(True))
    if sort == "recent":
        # `IS NULL` = true trong SQLite → đẩy file chưa mở xuống cuối
        stmt = stmt.order_by(
            Document.last_opened_at.is_(None), Document.last_opened_at.desc()
        )
    else:
        stmt = stmt.order_by(Document.created_at.desc())
    return list(db.scalars(stmt))


@router.post(
    "",
    response_model=DocumentOut,
    status_code=201,
    dependencies=[Depends(upload_rate_limit)],
)
async def upload_document(
    db: DbSession,
    current: CurrentUser,
    file: UploadFile = File(...),  # noqa: B008 — idiom FastAPI
    folder_id: uuid.UUID | None = Form(default=None),  # noqa: B008 — idiom FastAPI
) -> DocumentOut:
    """Upload 1 file; nếu là PDF thì ghi thêm số trang để UI hiển thị."""
    user = current

    if folder_id is not None:
        folder = db.get(Folder, folder_id)
        if folder is None or folder.owner_id != user.id:
            raise HTTPException(status_code=404, detail="Target folder not found")

    name = (file.filename or "khong-ten").strip()[:255]
    # MIME do server quyết định theo đuôi — kiểm tra TRƯỚC khi đọc nội dung
    mime = _resolve_upload_mime(name)

    max_bytes = get_settings().max_upload_mb * 1024 * 1024
    data = await _read_upload_limited(file, max_bytes)
    if not data:
        raise HTTPException(status_code=400, detail="File is empty")
    _ensure_storage_quota(db, user.id, len(data))

    key = storage_service.build_storage_key(name)
    storage_service.save_document_bytes(data, key)
    doc = Document(
        owner_id=user.id,
        folder_id=folder_id,
        original_name=name,
        storage_key=key,
        mime_type=mime,
        size_bytes=len(data),
        page_count=pdf_service.pdf_page_count(data) if mime == _PDF_MIME else None,
    )
    db.add(doc)
    db.flush()
    db.add(Permission(document_id=doc.id, user_id=user.id, role="owner"))
    db.commit()
    return DocumentOut.model_validate(doc)


@router.patch("/{document_id}/favorite", response_model=DocumentOut)
def set_favorite(
    document_id: uuid.UUID,
    body: FavoriteRequest,
    db: DbSession,
    current: CurrentUser,
) -> DocumentOut:
    """Gắn/gỡ sao tài liệu (TOOLS → Favorites)."""
    user = current
    doc = _get_owned_document(db, document_id, user.id)
    doc.is_favorite = body.favorite
    db.commit()
    return DocumentOut.model_validate(doc)


@router.post("/{document_id}/open", response_model=DocumentOut)
def mark_opened(
    document_id: uuid.UUID, db: DbSession, current: CurrentUser
) -> DocumentOut:
    """Đánh dấu tài liệu vừa được mở — cập nhật `last_opened_at` cho Recent."""
    user = current
    doc = _get_owned_document(db, document_id, user.id)
    doc.last_opened_at = datetime.now(UTC)
    db.commit()
    return DocumentOut.model_validate(doc)


@router.get("/usage", response_model=StorageUsageOut)
def get_storage_usage(db: DbSession, current: CurrentUser) -> StorageUsageOut:
    """Dung lượng tài liệu đã dùng và hạn mức của user (hiển thị ở trang Tài khoản)."""
    quota_mb = get_settings().user_storage_quota_mb
    return StorageUsageOut(
        used_bytes=_used_bytes(db, current.id),
        quota_bytes=quota_mb * 1024 * 1024 if quota_mb > 0 else None,
    )


@router.get("/{document_id}/download")
def download_document(
    document_id: uuid.UUID, db: DbSession, current: CurrentUser
) -> FileResponse:
    """Tải file gốc về máy.

    MIME lưu trong DB có thể do client khai từ trước (dữ liệu cũ) nên chỉ trả
    lại khi nằm trong danh sách an toàn; còn lại ép `application/octet-stream`
    để trình duyệt tải về thay vì render. `nosniff` chặn trình duyệt tự đoán
    kiểu nội dung (tránh stored XSS qua file upload).
    """
    user = current
    doc = _get_owned_document(db, document_id, user.id)
    try:
        path = storage_service.document_path(doc.storage_key)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail="Invalid storage key") from exc
    if not path.exists():
        raise HTTPException(status_code=410, detail="File is no longer available on the server")
    media_type = (
        doc.mime_type
        if doc.mime_type in _SAFE_DOWNLOAD_MIMES
        else "application/octet-stream"
    )
    return FileResponse(
        path,
        filename=doc.original_name,
        media_type=media_type,
        headers={"X-Content-Type-Options": "nosniff"},
    )


@router.delete("/{document_id}")
def delete_document(
    document_id: uuid.UUID, db: DbSession, current: CurrentUser
) -> dict[str, str]:
    user = current
    doc = _get_owned_document(db, document_id, user.id)
    # Xóa file các bản cũ TRƯỚC khi cascade xóa row — unlink(missing_ok=True)
    # nên trùng storage_key (sau khi restore) cũng an toàn.
    for version in list(doc.versions):
        storage_service.delete_document_file(version.storage_key)
    storage_service.delete_document_file(doc.storage_key)
    db.delete(doc)
    db.commit()
    return {"detail": "Document deleted"}


@router.post("/merge", response_model=DocumentOut, status_code=201)
def merge_documents(body: MergeRequest, db: DbSession, current: CurrentUser) -> DocumentOut:
    """Gộp nhiều PDF thành 1 tài liệu mới (không hủy bản gốc)."""
    user = current
    docs = [_get_owned_document(db, document_id, user.id) for document_id in body.document_ids]
    parts = []
    for doc in docs:
        if doc.mime_type != _PDF_MIME:
            raise HTTPException(status_code=400, detail=f"{doc.original_name} is not a PDF")
        parts.append(storage_service.read_document_bytes(doc.storage_key))
    try:
        merged = pdf_service.merge_pdfs(parts)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    name = body.name if body.name.lower().endswith(".pdf") else f"{body.name}.pdf"
    doc = _save_new_pdf_document(
        db, owner_id=user.id, data=merged, name=name, folder_id=docs[0].folder_id
    )
    db.commit()
    return DocumentOut.model_validate(doc)


@router.post("/{document_id}/split", response_model=list[DocumentOut], status_code=201)
def split_document(
    document_id: uuid.UUID, body: SplitRequest, db: DbSession, current: CurrentUser
) -> list[DocumentOut]:
    """Tách trang: mỗi phạm vi (vd "1-3,5") tạo 1 tài liệu PDF mới."""
    user = current
    doc = _get_owned_document(db, document_id, user.id)
    if doc.mime_type != _PDF_MIME:
        raise HTTPException(status_code=400, detail="Only PDF files can be split")
    data = storage_service.read_document_bytes(doc.storage_key)

    total = pdf_service.pdf_page_count(data)
    if total is None:
        raise HTTPException(status_code=400, detail="The PDF file cannot be read")
    try:
        ranges = pdf_service.parse_page_ranges(body.ranges, total)
        parts = pdf_service.split_pdf(data, ranges)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    base = doc.original_name.removesuffix(".pdf")
    created: list[Document] = []
    for (start, end), part in zip(ranges, parts, strict=True):
        label = f"trang {start}-{end}" if start != end else f"trang {start}"
        created.append(
            _save_new_pdf_document(
                db, owner_id=user.id, data=part,
                name=f"{base} ({label}).pdf", folder_id=doc.folder_id,
            )
        )
    db.commit()
    return [DocumentOut.model_validate(d) for d in created]


@router.post("/{document_id}/protect", response_model=DocumentOut, status_code=201)
def protect_document(
    document_id: uuid.UUID, body: ProtectRequest, db: DbSession, current: CurrentUser
) -> DocumentOut:
    """Tạo bản sao đã đặt mật khẩu (bản gốc giữ nguyên)."""
    user = current
    doc = _get_owned_document(db, document_id, user.id)
    if doc.mime_type != _PDF_MIME:
        raise HTTPException(status_code=400, detail="Only PDF files are supported")
    data = storage_service.read_document_bytes(doc.storage_key)
    # Đếm trang TRƯỚC khi mã hóa — PDF mã hóa đọc được số trang khó
    total_pages = pdf_service.pdf_page_count(data)
    try:
        protected = pdf_service.protect_pdf(data, body.password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    base = doc.original_name.removesuffix(".pdf")
    new_doc = _save_new_pdf_document(
        db, owner_id=user.id, data=protected,
        name=f"{base} (mat-khau).pdf", folder_id=doc.folder_id,
    )
    new_doc.page_count = total_pages
    db.commit()
    return DocumentOut.model_validate(new_doc)


@router.post("/{document_id}/unprotect", response_model=DocumentOut, status_code=201)
def unprotect_document(
    document_id: uuid.UUID, body: UnprotectRequest, db: DbSession, current: CurrentUser
) -> DocumentOut:
    """Tạo bản sao đã gỡ mật khẩu (cần mật khẩu hiện tại)."""
    user = current
    doc = _get_owned_document(db, document_id, user.id)
    if doc.mime_type != _PDF_MIME:
        raise HTTPException(status_code=400, detail="Only PDF files are supported")
    data = storage_service.read_document_bytes(doc.storage_key)
    try:
        unprotected = pdf_service.unprotect_pdf(data, body.password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    base = doc.original_name.removesuffix(".pdf")
    new_doc = _save_new_pdf_document(
        db, owner_id=user.id, data=unprotected,
        name=f"{base} (da-go-mat-khau).pdf", folder_id=doc.folder_id,
    )
    db.commit()
    return DocumentOut.model_validate(new_doc)


# -- Chia sẻ link công khai (SRS P1) + bình luận ghim (P2) --------------------


@router.post("/{document_id}/shares", response_model=ShareOut, status_code=201)
def create_share_link(
    document_id: uuid.UUID, body: ShareCreate, db: DbSession, current: CurrentUser
) -> ShareOut:
    """Tạo link chia sẻ. Raw token trả đúng 1 lần trong `share_url` (FR-1)."""
    user = current
    doc = _get_owned_document(db, document_id, user.id)
    share, token = share_service.create_share(
        db,
        document=doc,
        permission=body.permission,
        expires_in_hours=body.expires_in_hours,
    )
    return ShareOut(
        id=share.id,
        permission=share.permission,
        expires_at=share.expires_at,
        is_active=share.is_active,
        view_count=share.view_count,
        share_url=share_service.build_share_url(token),
        created_at=share.created_at,
    )


@router.get("/{document_id}/shares", response_model=list[ShareOut])
def list_share_links(
    document_id: uuid.UUID, db: DbSession, current: CurrentUser
) -> list[ShareOut]:
    """Danh sách mọi link (gồm đã thu hồi/hết hạn) — FR-1.4."""
    user = current
    doc = _get_owned_document(db, document_id, user.id)
    return [
        ShareOut(
            id=s.id,
            permission=s.permission,
            expires_at=s.expires_at,
            is_active=s.is_active,
            view_count=s.view_count,
            share_url="",  # raw token không lưu — không thể hiện lại
            created_at=s.created_at,
        )
        for s in share_service.list_shares(db, doc)
    ]


@router.delete("/{document_id}/shares/{share_id}", status_code=204)
def revoke_share_link(
    document_id: uuid.UUID, share_id: uuid.UUID, db: DbSession, current: CurrentUser
) -> None:
    """Thu hồi link — link chết ngay, không có "bỏ thu hồi" (FR-1.5)."""
    user = current
    doc = _get_owned_document(db, document_id, user.id)
    share_service.revoke_share(db, doc, share_id)


@router.get("/{document_id}/share-comments", response_model=list[OwnerShareCommentOut])
def list_share_comments_for_owner(
    document_id: uuid.UUID, db: DbSession, current: CurrentUser
) -> list[OwnerShareCommentOut]:
    """Mọi comment của mọi link thuộc tài liệu (P2, FR-6.5)."""
    user = current
    doc = _get_owned_document(db, document_id, user.id)
    result: list[OwnerShareCommentOut] = []
    for comment in share_service.list_all_comments_for_owner(db, doc):
        out = OwnerShareCommentOut.model_validate(comment)
        out.share_id = comment.share_id
        result.append(out)
    return result


@router.delete("/{document_id}/share-comments/{comment_id}", status_code=204)
def delete_share_comment(
    document_id: uuid.UUID, comment_id: uuid.UUID, db: DbSession, current: CurrentUser
) -> None:
    """Chủ tài liệu xóa comment bất kỳ của link chia sẻ (P2, FR-4.7)."""
    user = current
    doc = _get_owned_document(db, document_id, user.id)
    share_service.delete_comment_as_owner(db, doc, comment_id)
