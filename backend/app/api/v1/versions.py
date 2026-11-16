"""Endpoints lịch sử phiên bản tài liệu: upload bản mới, liệt kê, khôi phục,
tải bản cũ, xóa bản cũ, so sánh 2 bản (diff cục bộ + tóm tắt AI).

Nguyên tắc: bản hiện tại không bao giờ bị ghi đè mất — upload bản mới thì file
cũ được hạ thành phiên bản; khôi phục chỉ đổi con trỏ storage_key, file của
bản đang hiện tại cũng được giữ lại thành một phiên bản.

Lưu ý chi tiết về storage_key: sau khi khôi phục, tài liệu và một row phiên bản
có thể trỏ CÙNG một file — xóa phiên bản phải kiểm tra không ai khác dùng file
đó nữa mới được xóa file (xem [_delete_version]).

Đánh số phiên bản: 1 = gần nhất bị thay, 2 = cũ hơn… Việc "đẩy số lên 1" phải
làm 2 pha (sang số âm rồi sang số cuối) vì ràng buộc UNIQUE(document_id,
version_number) sẽ vỡ nếu UPDATE thẳng v1→2 khi DB còn row v2 cũ.
"""

import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session as DatabaseSession

from app.api.deps import CurrentUser, DbSession, ai_rate_limit, upload_rate_limit
from app.api.v1.documents import (
    _PDF_MIME,
    _SAFE_DOWNLOAD_MIMES,
    _ensure_storage_quota,
    _get_owned_document,
    _read_upload_limited,
    _resolve_upload_mime,
)
from app.core.config import get_settings
from app.models.document import Document
from app.models.document_version import MAX_VERSIONS_PER_DOCUMENT, DocumentVersion
from app.schemas.documents import (
    DocumentOut,
    DocumentVersionOut,
    VersionDiffRequest,
    VersionDiffResult,
)
from app.services import ai_service, credit_service, diff_service, pdf_service, storage_service

router = APIRouter(
    prefix="/documents/{document_id}/versions",
    tags=["versions"],
)


# ---------------------------------------------------------------------------
# Helpers


def _get_owned_version(
    db: DatabaseSession, document: Document, version_id: uuid.UUID
) -> DocumentVersion:
    """Lấy phiên bản thuộc đúng tài liệu, không có → 404."""
    version = db.get(DocumentVersion, version_id)
    if version is None or version.document_id != document.id:
        raise HTTPException(status_code=404, detail="Version not found")
    return version


def _versions_desc(db: DatabaseSession, document: Document) -> list[DocumentVersion]:
    """Danh sách phiên bản cũ, mới nhất đứng trước."""
    return list(
        db.scalars(
            select(DocumentVersion)
            .where(DocumentVersion.document_id == document.id)
            .order_by(DocumentVersion.version_number.desc())
        )
    )


def _delete_version(db: DatabaseSession, document: Document, version: DocumentVersion) -> None:
    """Xóa một phiên bản: row luôn bị xóa, file chỉ xóa khi không còn ai trỏ.

    Sau khi khôi phục, tài liệu (bản hiện tại) có thể trỏ cùng storage_key với
    row phiên bản — xóa file lúc đó sẽ làm hỏng bản hiện tại.
    """
    still_referenced = version.storage_key == document.storage_key or any(
        v.storage_key == version.storage_key for v in _versions_desc(db, document)
        if v.id != version.id
    )
    if not still_referenced:
        storage_service.delete_document_file(version.storage_key)
    db.delete(version)


def _prune_overflow_versions(db: DatabaseSession, document: Document) -> None:
    """Giữ tối đa [MAX_VERSIONS_PER_DOCUMENT] bản cũ — vượt thì xóa bản cũ nhất."""
    overflow = _versions_desc(db, document)[MAX_VERSIONS_PER_DOCUMENT:]
    for version in overflow:
        _delete_version(db, document, version)


def _version_download_name(document: Document, version: DocumentVersion) -> str:
    """Tên file khi tải bản cũ: `hop-dong.pdf` → `hop-dong (v2).pdf`."""
    base = document.original_name
    stem, dot, ext = base.rpartition(".")
    if not stem:
        return f"{base} (v{version.version_number})"
    return f"{stem} (v{version.version_number}){dot}{ext}"


def _archive_current_as_version(db: DatabaseSession, document: Document, label: str) -> None:
    """Hạ bản hiện tại thành phiên bản 1, đẩy số các bản cũ lên 1 (2 pha)."""
    versions = _versions_desc(db, document)
    # Pha 1: sang số âm (đảm bảo không đụng ràng buộc UNIQUE khi UPDATE)
    for version in versions:
        version.version_number = -version.version_number
    db.flush()
    # Pha 2: gán số cuối cùng (dương, dồn lên 1)
    for version in versions:
        version.version_number = -version.version_number + 1
    db.flush()
    db.add(
        DocumentVersion(
            document_id=document.id,
            version_number=1,
            storage_key=document.storage_key,
            size_bytes=document.size_bytes,
            page_count=document.page_count,
            label=label,
        )
    )
    db.flush()


# ---------------------------------------------------------------------------
# Endpoints


@router.post("", response_model=DocumentOut, status_code=201,
             dependencies=[Depends(upload_rate_limit)])
async def upload_new_version(
    document_id: uuid.UUID,
    db: DbSession,
    current: CurrentUser,
    file: UploadFile = File(...),  # noqa: B008 — idiom FastAPI
    label: str = Form(default=""),  # noqa: B008 — idiom FastAPI
) -> DocumentOut:
    """Upload bản mới: file hiện tại thành phiên bản 1, file mới thay thế làm
    bản hiện tại (giữ nguyên id/thư mục/sao nên UI không đổi chỗ)."""
    user = current
    document = _get_owned_document(db, document_id, user.id)

    name = (file.filename or "").strip()[:255]
    mime = _resolve_upload_mime(name)
    if mime != document.mime_type:
        raise HTTPException(
            status_code=400,
            detail=(
                "New version must be the same file type as the document "
                f"({document.mime_type})"
            ),
        )

    max_bytes = get_settings().max_upload_mb * 1024 * 1024
    data = await _read_upload_limited(file, max_bytes)
    if not data:
        raise HTTPException(status_code=400, detail="File is empty")
    _ensure_storage_quota(db, user.id, len(data))

    _archive_current_as_version(db, document, label.strip()[:200])

    key = storage_service.build_storage_key(name)
    storage_service.save_document_bytes(data, key)
    document.storage_key = key
    document.size_bytes = len(data)
    document.page_count = (
        pdf_service.pdf_page_count(data) if mime == _PDF_MIME else None
    )
    _prune_overflow_versions(db, document)
    db.commit()
    return DocumentOut.model_validate(document)


@router.get("", response_model=list[DocumentVersionOut])
def list_versions(
    document_id: uuid.UUID, db: DbSession, current: CurrentUser
) -> list[DocumentVersionOut]:
    """Danh sách phiên bản cũ (mới nhất trước)."""
    user = current
    document = _get_owned_document(db, document_id, user.id)
    return [DocumentVersionOut.model_validate(v) for v in _versions_desc(db, document)]


@router.get("/{version_id}/download")
def download_version(
    document_id: uuid.UUID,
    version_id: uuid.UUID,
    db: DbSession,
    current: CurrentUser,
) -> FileResponse:
    """Tải file của một bản cũ về máy."""
    user = current
    document = _get_owned_document(db, document_id, user.id)
    version = _get_owned_version(db, document, version_id)
    try:
        path = storage_service.document_path(version.storage_key)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail="Invalid storage key") from exc
    if not path.exists():
        raise HTTPException(
            status_code=410, detail="File is no longer available on the server"
        )
    media_type = (
        document.mime_type
        if document.mime_type in _SAFE_DOWNLOAD_MIMES
        else "application/octet-stream"
    )
    return FileResponse(
        path,
        filename=_version_download_name(document, version),
        media_type=media_type,
        headers={"X-Content-Type-Options": "nosniff"},
    )


@router.post("/{version_id}/restore", response_model=DocumentOut)
def restore_version(
    document_id: uuid.UUID,
    version_id: uuid.UUID,
    db: DbSession,
    current: CurrentUser,
) -> DocumentOut:
    """Khôi phục một bản cũ thành bản hiện tại.

    Bản đang hiện tại được hạ thành phiên bản 1 (không mất), storage_key của
    tài liệu trỏ lại file của bản được khôi phục. Bản được khôi phục vẫn giữ
    row trong lịch sử (điểm khôi phục an toàn) — hai row tạm trùng file,
    [delete_version] đã xử lý xóa an toàn trường hợp này.
    """
    user = current
    document = _get_owned_document(db, document_id, user.id)
    version = _get_owned_version(db, document, version_id)
    _ensure_storage_quota(db, user.id, 0)

    _archive_current_as_version(db, document, label="")
    document.storage_key = version.storage_key
    document.size_bytes = version.size_bytes
    document.page_count = version.page_count
    _prune_overflow_versions(db, document)
    db.commit()
    return DocumentOut.model_validate(document)


@router.delete("/{version_id}")
def delete_version(
    document_id: uuid.UUID,
    version_id: uuid.UUID,
    db: DbSession,
    current: CurrentUser,
) -> dict[str, str]:
    """Xóa một bản cũ khỏi lịch sử (file + row). Bản hiện tại không nằm trong
    lịch sử nên không thể xóa nhầm."""
    user = current
    document = _get_owned_document(db, document_id, user.id)
    version = _get_owned_version(db, document, version_id)
    _delete_version(db, document, version)
    db.commit()
    return {"detail": "Version deleted"}


@router.post("/diff", response_model=VersionDiffResult,
             dependencies=[Depends(ai_rate_limit)])
def diff_versions(
    document_id: uuid.UUID,
    body: VersionDiffRequest,
    db: DbSession,
    current: CurrentUser,
) -> VersionDiffResult:
    """So sánh 2 bản: diff dòng cục bộ (miễn phí) + tóm tắt thay đổi bằng AI.

    `new_version_id=None` so bản cũ với bản hiện tại. Trích văn bản cục bộ
    (pypdf/python-docx) — tài liệu scan chưa có lớp text sẽ báo lỗi hướng dẫn.
    Hai bản không khác gì thì trả ngay, không trừ credit.
    """
    user = current
    document = _get_owned_document(db, document_id, user.id)
    old = _get_owned_version(db, document, body.old_version_id)

    if not ai_service.is_text_extractable(document.mime_type, document.original_name):
        raise HTTPException(
            status_code=415,
            detail=(
                "Version compare needs readable text (PDF, Word, txt). "
                "Scanned files must be OCR-ed first."
            ),
        )

    def _text_of(storage_key: str) -> str:
        return ai_service.extract_document_text(
            storage_service.read_document_bytes(storage_key),
            document.mime_type,
            document.original_name,
        )

    try:
        old_text = _text_of(old.storage_key)
        if body.new_version_id is None:
            new_text = _text_of(document.storage_key)
        else:
            new = _get_owned_version(db, document, body.new_version_id)
            new_text = _text_of(new.storage_key)
    except ai_service.AIServiceError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    diff = diff_service.compute_line_diff(old_text, new_text)
    stats = diff_service.diff_stats(diff)
    if not diff:
        # Giống hệt nhau — không gọi AI, không trừ credit.
        return VersionDiffResult(diff=[], added=0, removed=0, ai_summary=None)

    # Tóm tắt AI: trừ credit trước, lỗi thì hoàn (đúng pattern các API AI).
    try:
        credit_service.charge(db, user)
    except credit_service.InsufficientCredits as exc:
        raise HTTPException(status_code=402, detail=str(exc)) from exc
    try:
        summary = diff_service.summarize_changes(old_text, new_text)
    except ai_service.AIServiceError as exc:
        credit_service.refund(db, user)
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return VersionDiffResult(
        diff=diff[:2000],
        added=stats["added"],
        removed=stats["removed"],
        ai_summary=summary,
    )
