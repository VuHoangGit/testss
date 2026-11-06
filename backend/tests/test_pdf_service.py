"""Test pdf_service: đếm trang, gộp, tách, đặt/gỡ mật khẩu (Sprint 2)."""

import io

import pytest
from pypdf import PdfReader, PdfWriter

from app.services import pdf_service


def make_pdf(pages: int) -> bytes:
    """Tạo PDF mẫu có N trang trắng (không cần file ngoài)."""
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=200, height=200)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


class TestPageCount:
    def test_counts_pages(self):
        assert pdf_service.pdf_page_count(make_pdf(3)) == 3

    def test_not_a_pdf_returns_none(self):
        assert pdf_service.pdf_page_count(b"khong phai pdf") is None
        assert pdf_service.pdf_page_count(b"") is None


class TestMerge:
    def test_merge_two_pdfs(self):
        merged = pdf_service.merge_pdfs([make_pdf(2), make_pdf(3)])
        assert pdf_service.pdf_page_count(merged) == 5

    def test_merge_invalid_part_raises_value_error(self):
        with pytest.raises(ValueError, match="not a readable PDF"):
            pdf_service.merge_pdfs([make_pdf(1), b"rac"])

    def test_merge_encrypted_part_raises_value_error(self):
        locked = pdf_service.protect_pdf(make_pdf(1), "mk")
        with pytest.raises(ValueError, match="is encrypted"):
            pdf_service.merge_pdfs([locked])


class TestParseRanges:
    def test_single_and_range(self):
        assert pdf_service.parse_page_ranges("1-3,5", 10) == [(1, 3), (5, 5)]

    def test_out_of_bounds_raises(self):
        with pytest.raises(ValueError, match="is outside the document"):
            pdf_service.parse_page_ranges("1-11", 10)

    def test_reversed_range_raises(self):
        with pytest.raises(ValueError, match="5-2"):
            pdf_service.parse_page_ranges("5-2", 10)

    def test_garbage_raises(self):
        with pytest.raises(ValueError):
            pdf_service.parse_page_ranges("abc", 10)

    def test_empty_raises(self):
        with pytest.raises(ValueError, match="No page ranges provided"):
            pdf_service.parse_page_ranges("  ", 10)


class TestSplit:
    def test_split_creates_expected_page_counts(self):
        data = make_pdf(5)
        parts = pdf_service.split_pdf(data, [(1, 2), (3, 3), (4, 5)])
        assert [pdf_service.pdf_page_count(p) for p in parts] == [2, 1, 2]

    def test_split_encrypted_raises(self):
        locked = pdf_service.protect_pdf(make_pdf(2), "mk")
        with pytest.raises(ValueError, match="is encrypted"):
            pdf_service.split_pdf(locked, [(1, 1)])


class TestProtectUnprotect:
    def test_protect_then_open_needs_password(self):
        locked = pdf_service.protect_pdf(make_pdf(2), "matkhau123")
        reader = PdfReader(io.BytesIO(locked))
        assert reader.is_encrypted
        with pytest.raises(Exception):  # noqa: B017 — pypdf nổ nhiều loại khi thiếu mật khẩu
            len(reader.pages)

    def test_unprotect_with_correct_password(self):
        locked = pdf_service.protect_pdf(make_pdf(2), "matkhau123")
        unlocked = pdf_service.unprotect_pdf(locked, "matkhau123")
        assert pdf_service.pdf_page_count(unlocked) == 2
        assert not PdfReader(io.BytesIO(unlocked)).is_encrypted

    def test_unprotect_wrong_password_raises(self):
        locked = pdf_service.protect_pdf(make_pdf(2), "matkhau123")
        with pytest.raises(ValueError, match="Incorrect password"):
            pdf_service.unprotect_pdf(locked, "sai-roi")

    def test_unprotect_plain_document_raises(self):
        with pytest.raises(ValueError, match="has no password"):
            pdf_service.unprotect_pdf(make_pdf(1), "bat-ky")

    def test_protect_encrypted_document_raises(self):
        locked = pdf_service.protect_pdf(make_pdf(1), "mk")
        with pytest.raises(ValueError, match="already has a password"):
            pdf_service.protect_pdf(locked, "mk2")
