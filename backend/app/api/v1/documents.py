"""Endpoints tài liệu: upload (multipart), list, download, xóa + công cụ PDF
(gộp / tách trang / mật khẩu) bằng pypdf phía server (Sprint 2).
"""

import uuid

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session as DatabaseSession

from app.api.deps import CurrentUser, DbSession
from app.core.config import get_settings
from app.models.document import Document
from app.models.folder import Folder
from app.models.permission import Permission
from app.schemas.documents import (
    DocumentOut,
    MergeRequest,
    ProtectRequest,
    SplitRequest,
    UnprotectRequest,
)
from app.services import pdf_service, storage_service

router = APIRouter(prefix="/documents", tags=["documents"])

_PDF_MIME = "application/pdf"


def _get_owned_document(db: DatabaseSession, document_id: uuid.UUID, user_id) -> Document:
    doc = db.get(Document, document_id)
    if doc is None or doc.owner_id != user_id:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài liệu")
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
) -> list[DocumentOut]:
    """Danh sách tài liệu của user; truy vấn `folder_id` để lọc theo thư mục."""
    _, user = current
    stmt = select(Document).where(Document.owner_id == user.id)
    if folder_id is not None:
        stmt = stmt.where(Document.folder_id == folder_id)
    return list(db.scalars(stmt.order_by(Document.created_at.desc())))


@router.post("", response_model=DocumentOut, status_code=201)
async def upload_document(
    db: DbSession,
    current: CurrentUser,
    file: UploadFile = File(...),  # noqa: B008 — idiom FastAPI
    folder_id: uuid.UUID | None = Form(default=None),  # noqa: B008 — idiom FastAPI
) -> DocumentOut:
    """Upload 1 file; nếu là PDF thì ghi thêm số trang để UI hiển thị."""
    _, user = current

    if folder_id is not None:
        folder = db.get(Folder, folder_id)
        if folder is None or folder.owner_id != user.id:
            raise HTTPException(status_code=404, detail="Không tìm thấy thư mục đích")

    max_bytes = get_settings().max_upload_mb * 1024 * 1024
    data = await file.read()
    if len(data) > max_bytes:
        raise HTTPException(
            status_code=413, detail=f"File vượt quá {get_settings().max_upload_mb} MB"
        )
    if not data:
        raise HTTPException(status_code=400, detail="File rỗng")

    name = (file.filename or "khong-ten").strip()[:255]
    mime = file.content_type or "application/octet-stream"
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


@router.get("/{document_id}/download")
def download_document(
    document_id: uuid.UUID, db: DbSession, current: CurrentUser
) -> FileResponse:
    """Tải file gốc về máy."""
    _, user = current
    doc = _get_owned_document(db, document_id, user.id)
    try:
        path = storage_service.document_path(doc.storage_key)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail="Storage key không hợp lệ") from exc
    if not path.exists():
        raise HTTPException(status_code=410, detail="File không còn trên máy chủ")
    return FileResponse(path, filename=doc.original_name, media_type=doc.mime_type)


@router.delete("/{document_id}")
def delete_document(
    document_id: uuid.UUID, db: DbSession, current: CurrentUser
) -> dict[str, str]:
    _, user = current
    doc = _get_owned_document(db, document_id, user.id)
    storage_service.delete_document_file(doc.storage_key)
    db.delete(doc)
    db.commit()
    return {"detail": "Đã xóa tài liệu"}


@router.post("/merge", response_model=DocumentOut, status_code=201)
def merge_documents(body: MergeRequest, db: DbSession, current: CurrentUser) -> DocumentOut:
    """Gộp nhiều PDF thành 1 tài liệu mới (không hủy bản gốc)."""
    _, user = current
    docs = [_get_owned_document(db, document_id, user.id) for document_id in body.document_ids]
    parts = []
    for doc in docs:
        if doc.mime_type != _PDF_MIME:
            raise HTTPException(status_code=400, detail=f"{doc.original_name} không phải PDF")
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
    _, user = current
    doc = _get_owned_document(db, document_id, user.id)
    if doc.mime_type != _PDF_MIME:
        raise HTTPException(status_code=400, detail="Chỉ hỗ trợ tách file PDF")
    data = storage_service.read_document_bytes(doc.storage_key)

    total = pdf_service.pdf_page_count(data)
    if total is None:
        raise HTTPException(status_code=400, detail="File PDF không đọc được")
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
    _, user = current
    doc = _get_owned_document(db, document_id, user.id)
    if doc.mime_type != _PDF_MIME:
        raise HTTPException(status_code=400, detail="Chỉ hỗ trợ file PDF")
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
    _, user = current
    doc = _get_owned_document(db, document_id, user.id)
    if doc.mime_type != _PDF_MIME:
        raise HTTPException(status_code=400, detail="Chỉ hỗ trợ file PDF")
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
