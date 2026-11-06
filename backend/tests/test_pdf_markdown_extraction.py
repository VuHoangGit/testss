"""Test suy cấu trúc từ PDF lớp text: dòng tiêu đề (cỡ chữ lớn) → `#`/`##`/`###`.

Vì sao cần: `pypdf` trích chữ thuần nên bản xuất Word mất outline level. Ở đây
kiểm bằng PDF tự dựng (Helvetica, mỗi dòng một cỡ chữ) để biết tỉ lệ cỡ chữ
đúng như tài liệu thật.
"""

import io

import pytest
from pypdf import PdfReader

from app.services import ai_service


def _build_pdf(lines: list[tuple[float, str]]) -> bytes:
    """PDF 1 trang A4: mỗi dòng vẽ ở cỡ chữ cho trước, xuống dần theo trục y."""
    content = b""
    y = 780
    for size, text in lines:
        content += f"BT /F1 {size} Tf 72 {y} Td ({text}) Tj ET\n".encode()
        y -= size + 12

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
        b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]

    output = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(output))
        output += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    xref_at = len(output)
    output += f"xref\n0 {len(objects) + 1}\n".encode() + b"0000000000 65535 f \n"
    for offset in offsets:
        output += f"{offset:010d} 00000 n \n".encode()
    output += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_at}\n%%EOF\n"
    ).encode()
    return bytes(output)


def _pages(lines: list[tuple[float, str]]) -> list[str]:
    return ai_service.extract_pdf_pages_markdown(_build_pdf(lines))


def test_large_font_lines_become_headings_of_matching_level():
    pages = _pages(
        [
            (18.0, "CHUONG 1 MO DAU"),  # 1.8x thân 10pt
            (14.0, "1.1 Tieu de muc con"),  # 1.4x
            (12.0, "1.1.1 Muc nho hon"),  # 1.2x
            (10.0, "Day la dong noi dung binh thuong cua tai lieu."),
            (10.0, "Dong noi dung thu hai."),
        ]
    )

    lines = pages[0].split("\n")
    assert lines[0] == "# CHUONG 1 MO DAU"
    assert lines[1] == "## 1.1 Tieu de muc con"
    assert lines[2] == "### 1.1.1 Muc nho hon"
    assert lines[3] == "Day la dong noi dung binh thuong cua tai lieu."


def test_body_size_is_the_most_used_size():
    """Cỡ chữ thân = cỡ phổ biến nhất, không phải cỡ lớn nhất của tiêu đề."""
    pages = _pages(
        [
            (30.0, "TIEU DE RAT LON"),
            (12.0, "Mot doan van dai binh thuong nam trong than tai lieu."),
            (12.0, "Mot doan van dai binh thuong nam trong than tai lieu."),
        ]
    )

    assert pages[0].split("\n")[0] == "# TIEU DE RAT LON"


def test_plain_document_has_no_markdown_markers():
    pages = _pages([(12.0, "Mot dong binh thuong."), (12.0, "Mot dong khac.")])

    assert "#" not in pages[0]


def test_uniform_font_document_keeps_all_lines_plain():
    pages = _pages([(14.0, "Dong thu nhat."), (14.0, "Dong thu hai.")])

    assert pages[0] == "Dong thu nhat.\nDong thu hai."


def test_font_size_zero_does_not_produce_headings(monkeypatch):
    """PDF không khai báo cỡ chữ → không đoán bừa."""
    assert ai_service._heading_level(0, 12) == 0
    assert ai_service._heading_level(12, 0) == 0


def test_single_page_text_layer_still_readable_by_ocr(monkeypatch):
    """Luồng OCR dùng bản có cấu trúc: trang 1 trang vẫn là text-layer."""
    data = _build_pdf([(12.0, "Noi dung mot trang.")])

    pages = ai_service.extract_pdf_pages_markdown(data)

    assert len(pages) == 1
    assert pages[0].strip() == "Noi dung mot trang."
    # hàm cũ (dùng cho dịch/tóm tắt) vẫn giữ hành vi thuần chữ
    assert ai_service.extract_pdf_pages(data)[0].strip() == "Noi dung mot trang."


def test_encrypted_pdf_raises_friendly_error():
    reader = PdfReader(io.BytesIO(_build_pdf([(12.0, "Noi dung.")])))
    protected = _writer_from(reader)

    with pytest.raises(ai_service.AIServiceError) as error:
        ai_service.extract_pdf_pages_markdown(protected)

    assert "encrypted" in str(error.value)


def _writer_from(reader: PdfReader) -> bytes:
    """PDF có mật khẩu → nhánh lỗi phải báo tiếng người, không crash."""
    from pypdf import PdfWriter

    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    writer.encrypt("secret")
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()
