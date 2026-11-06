"""Công cụ PDF chạy trên server bằng pypdf (Sprint 2):
gộp, tách trang, đặt/gỡ mật khẩu. Mọi hàm nhận/trả bytes, không đụng DB.
"""

import io
import re

from pypdf import PdfReader, PdfWriter


def _reader(data: bytes) -> PdfReader:
    return PdfReader(io.BytesIO(data))


def _write_bytes(writer: PdfWriter) -> bytes:
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def pdf_page_count(data: bytes) -> int | None:
    """Số trang nếu là PDF hợp lệ; file khác/hỏng → None (không chặn upload)."""
    try:
        return len(_reader(data).pages)
    except Exception:  # noqa: BLE001 — pypdf nổ nhiều loại lỗi, đều coi như "không đọc được"
        return None


def merge_pdfs(parts: list[bytes]) -> bytes:
    """Gộp nhiều PDF theo thứ tự; file hỏng/đang mã hóa → ValueError."""
    writer = PdfWriter()
    for index, part in enumerate(parts):
        try:
            reader = _reader(part)
            if reader.is_encrypted:
                raise ValueError(f"File {index + 1} is encrypted, remove its password first")
            writer.append(reader)
        except ValueError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ValueError(f"File {index + 1} is not a readable PDF") from exc
    return _write_bytes(writer)


def parse_page_ranges(spec: str, total_pages: int) -> list[tuple[int, int]]:
    """Parse "1-3,5" thành các khoảng 1-based inclusive; sai cú pháp → ValueError."""
    spec = (spec or "").replace(" ", "")
    if not spec:
        raise ValueError("No page ranges provided")
    ranges: list[tuple[int, int]] = []
    for chunk in spec.split(","):
        m = re.fullmatch(r"(\d+)(?:-(\d+))?", chunk)
        if not m:
            raise ValueError(f"Invalid range: {chunk!r}")
        start = int(m.group(1))
        end = int(m.group(2)) if m.group(2) else start
        if start < 1 or end < start or end > total_pages:
            raise ValueError(f"Range {start}-{end} is outside the document ({total_pages} pages)")
        ranges.append((start, end))
    return ranges


def split_pdf(data: bytes, ranges: list[tuple[int, int]]) -> list[bytes]:
    """Tách 1 PDF thành nhiều PDF theo các khoảng trang."""
    reader = _reader(data)
    if reader.is_encrypted:
        raise ValueError("The document is encrypted, remove its password first")
    results: list[bytes] = []
    for start, end in ranges:
        writer = PdfWriter()
        for i in range(start - 1, end):
            writer.add_page(reader.pages[i])
        results.append(_write_bytes(writer))
    return results


def protect_pdf(data: bytes, password: str) -> bytes:
    """Đặt mật khẩu mở file (AES-256, cần package cryptography)."""
    reader = _reader(data)
    if reader.is_encrypted:
        raise ValueError("The document already has a password")
    writer = PdfWriter()
    writer.append(reader)
    writer.encrypt(user_password=password, algorithm="AES-256")
    return _write_bytes(writer)


def unprotect_pdf(data: bytes, password: str) -> bytes:
    """Gỡ mật khẩu — sai mật khẩu → ValueError."""
    reader = _reader(data)
    if not reader.is_encrypted:
        raise ValueError("The document has no password")
    if reader.decrypt(password).value == 0:
        raise ValueError("Incorrect password")
    writer = PdfWriter()
    writer.append(reader)
    return _write_bytes(writer)
