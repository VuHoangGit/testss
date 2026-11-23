"""Router PUBLIC cho người nhận link chia sẻ — KHÔNG đăng nhập, rate limit theo IP.

Ranh giới "public" tách hẳn thành file: mọi endpoint ở đây không có dependency
CurrentUser và client không bao giờ gửi document_id — suy từ token hash.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse

from app.api.deps import DbSession
from app.api.v1.documents import _SAFE_DOWNLOAD_MIMES
from app.core.config import get_settings
from app.core.ratelimit import get_limiter
from app.models.user import User
from app.schemas.shares import (
    PublicShareMeta,
    ShareCommentCreate,
    ShareCommentOut,
)
from app.services import share_service, storage_service

router = APIRouter(prefix="/public/shares", tags=["public-shares"])

_PDF_MIME = "application/pdf"


def _client_ip(request: Request) -> str:
    """IP của người nhận (đằng sau proxy thì lấy X-Forwarded-For đầu tiên)."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",", 1)[0].strip()
    return request.client.host if request.client else "unknown"


def _enforce_ip_rate_limit(request: Request, group: str, max_calls: int) -> None:
    """Chặn IP vượt hạn mức → 429 + Retry-After (FR-2.6)."""
    if not get_settings().rate_limit_enabled:
        return
    retry_after = get_limiter(group).hit(f"ip:{_client_ip(request)}", max_calls, 60.0)
    if retry_after is not None:
        raise HTTPException(
            status_code=429,
            detail="Quá nhiều yêu cầu — thử lại sau ít phút",
            headers={"Retry-After": str(int(retry_after) + 1)},
        )


def meta_rate_limit(request: Request) -> None:
    _enforce_ip_rate_limit(request, "share-meta", get_settings().rate_limit_share_meta_per_minute)


def file_rate_limit(request: Request) -> None:
    _enforce_ip_rate_limit(request, "share-file", get_settings().rate_limit_share_file_per_minute)


def comment_rate_limit(request: Request) -> None:
    _enforce_ip_rate_limit(
        request,
        "share-comment",
        get_settings().rate_limit_share_comment_per_minute,
    )


@router.get("/{token}", response_model=PublicShareMeta, dependencies=[Depends(meta_rate_limit)])
def get_share_meta(token: str, db: DbSession) -> PublicShareMeta:
    """Metadata tài liệu cho người nhận — không trả id nội bộ (FR-2.1)."""
    share, document = share_service.resolve_share_or_404(db, token)
    owner = db.get(User, document.owner_id)
    return PublicShareMeta(
        file_name=document.original_name,
        mime_type=document.mime_type,
        size_bytes=document.size_bytes,
        page_count=document.page_count,
        permission=share.permission,
        expires_at=share.expires_at,
        owner_name=share_service.owner_display_name(owner) if owner else "Không rõ",
    )


@router.get("/{token}/file", dependencies=[Depends(file_rate_limit)])
def get_share_file(token: str, db: DbSession) -> FileResponse:
    """Stream file cho người nhận: PDF inline, loại khác attachment (FR-2.2).

    GET thành công tăng view_count (best-effort, FR-2.5).
    """
    share, document = share_service.resolve_share_or_404(db, token)
    try:
        path = storage_service.document_path(document.storage_key)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail="Lỗi lưu trữ") from exc
    if not path.exists():
        raise HTTPException(status_code=404, detail=share_service.LINK_NOT_FOUND)

    share.view_count += 1  # best-effort: commit cùng request, lỗi không chặn trả file
    db.commit()

    safe_name = share_service.sanitize_filename(document.original_name)
    inline = document.mime_type == _PDF_MIME
    # MIME lạ ép octet-stream + nosniff — chống sniff HTML trên origin API
    media_type = (
        document.mime_type
        if document.mime_type in _SAFE_DOWNLOAD_MIMES
        else "application/octet-stream"
    )
    return FileResponse(
        path,
        media_type=media_type,
        headers={
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": (
                f'inline; filename="{safe_name}"'
                if inline
                else f'attachment; filename="{safe_name}"'
            ),
        },
    )


# -- P2: bình luận ghim vị trí ------------------------------------------------


@router.get(
    "/{token}/comments",
    response_model=list[ShareCommentOut],
    dependencies=[Depends(meta_rate_limit)],
)
def list_share_comments(token: str, db: DbSession) -> list[ShareCommentOut]:
    """Danh sách comment của link, sort (page, created) — FR-5."""
    share, _document = share_service.resolve_share_or_404(db, token)
    return [
        ShareCommentOut.model_validate(c)
        for c in share_service.list_comments(db, share)
    ]


@router.post(
    "/{token}/comments",
    response_model=ShareCommentOut,
    status_code=201,
    dependencies=[Depends(comment_rate_limit)],
)
def create_share_comment(token: str, body: ShareCommentCreate, db: DbSession) -> ShareCommentOut:
    """Thêm comment. Link view → 403 'Link này chỉ cho phép xem' (FR-4.5)."""
    share, _document = share_service.resolve_share_or_404(db, token)
    comment = share_service.add_comment(db, share, body)
    return ShareCommentOut.model_validate(comment)
