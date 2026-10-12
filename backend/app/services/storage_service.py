"""Lưu file tài liệu lên đĩa cục bộ (Sprint 2).

Key do server sinh (uuid + đuôi) nên không bao giờ path traversal; sau này
đổi sang S3/GCS chỉ cần thay lớp này, API/router giữ nguyên.
"""

import uuid
from pathlib import Path

from app.core.config import get_settings


def documents_dir() -> Path:
    """Thư mục lưu file — tạo sẵn nếu chưa có."""
    settings = get_settings()
    base = Path(settings.documents_dir) if settings.documents_dir else Path("storage") / "documents"
    base.mkdir(parents=True, exist_ok=True)
    return base


def build_storage_key(original_name: str) -> str:
    suffix = Path(original_name).suffix.lower()[:16]
    return f"{uuid.uuid4().hex}{suffix}"


def save_document_bytes(data: bytes, key: str) -> None:
    path = documents_dir() / key
    path.write_bytes(data)


def document_path(key: str) -> Path:
    # Chặn path traversal: key phải là tên file thuần
    if Path(key).name != key or key in {".", ".."}:
        raise ValueError("Storage key không hợp lệ")
    return documents_dir() / key


def read_document_bytes(key: str) -> bytes:
    return document_path(key).read_bytes()


def delete_document_file(key: str) -> None:
    document_path(key).unlink(missing_ok=True)
