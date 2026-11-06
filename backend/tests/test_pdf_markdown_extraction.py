"""Test suy cấu trúc từ PDF lớp text: tiêu đề (`#`), đoạn văn, gạch đầu dòng.

Vì sao cần: `pypdf` trích chữ thuần nên bản xuất Word mất outline level, còn
`pdfium` thì bỏ mất dấu cách ở một số chỗ ("sựphát triển"). Ở đây kiểm bằng PDF
tự dựng (Helvetica, mỗi dòng một cỡ chữ) để biết tỉ lệ cỡ chữ đúng như tài liệu
thật, cộng thêm các test đơn vị cho phần gom đoạn.
"""

import io

import pytest
from pypdf import PdfReader

from app.services import ai_service


def _build_pdf_raw(content: bytes, pages: int = 1) -> bytes:
    """PDF tối giản với luồng nội dung cho trước (1 trang)."""
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


def _build_pdf(lines: list[tuple[float, str]]) -> bytes:
    """PDF 1 trang A4: mỗi dòng vẽ ở cỡ chữ cho trước, xuống dần theo trục y."""
    content = b""
    y = 780
    for size, text in lines:
        content += f"BT /F1 {size} Tf 72 {y} Td ({text}) Tj ET\n".encode()
        y -= size + 12
    return _build_pdf_raw(content)


def _pages(lines: list[tuple[float, str]]) -> list[str]:
    return ai_service.extract_pdf_pages_markdown(_build_pdf(lines))


def _line(
    text: str,
    size: float = 12.0,
    left: float = 50.0,
    right: float = 500.0,
    top: float = 700.0,
) -> ai_service._PdfLine:
    return ai_service._PdfLine(text, size, left, right, top)


# --- tiêu đề --------------------------------------------------------------


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


def test_heading_levels_use_page_local_font_size():
    """Trang vẽ qua phép biến đổi tỉ lệ (cỡ 200 thay vì 12) không thành toàn heading.

    CV thiết kế bằng Canva báo cỡ chữ 170–440 cho cả trang; lấy cỡ chuẩn của cả
    tài liệu (12) thì mọi dòng đều "to hơn thân" → cả trang thành Heading.
    """
    lines = [
        _line("MOT MUC", size=240.0, top=700.0),
        _line("Dong noi dung cua trang nay kha dai va la than van ban.", size=200.0, top=670.0),
        _line("Dong thu hai cung co cung co chu than van ban.", size=200.0, top=650.0),
    ]

    markdown = ai_service._lines_to_markdown(lines, ai_service._body_font_size([lines]))

    head, *body = markdown.split("\n")
    assert head == "### MOT MUC"  # 240/200 → cấp 3, không phải cả trang thành tiêu đề
    assert body == [
        "Dong noi dung cua trang nay kha dai va la than van ban. "
        "Dong thu hai cung co cung co chu than van ban."
    ]


def test_top_level_heading_is_promoted_to_level_one():
    """Tài liệu chỉ có 2 cỡ tiêu đề (14/12) vẫn ra Heading 1, không phải Heading 2."""

    pages = _pages(
        [
            (14.0, "1 Introduction"),  # 1.4x thân 10pt → cấp 2 nếu không dịch
            (12.0, "1.1 Chi tiet"),  # 1.2x → cấp 3
            (10.0, "Dong noi dung cua tai lieu."),
        ]
    )

    lines = pages[0].split("\n")
    assert lines[0] == "# 1 Introduction"
    assert lines[1] == "## 1.1 Chi tiet"
    assert lines[2] == "Dong noi dung cua tai lieu."


def test_heading_levels_document_with_all_three_levels_is_unchanged():
    """Đã có `#` sẵn thì không dịch gì (giữ đúng cấp gốc)."""
    pages = _pages(
        [
            (18.0, "CHUONG 1"),
            (14.0, "1.1 Muc"),
            (12.0, "1.1.1 Muc nho"),
            (10.0, "Noi dung cua tai lieu nam o day va dai hon moi tieu de."),
        ]
    )

    lines = pages[0].split("\n")
    assert [line.split(" ")[0] for line in lines[:3]] == ["#", "##", "###"]


def test_font_size_zero_does_not_produce_headings():
    """PDF không khai báo cỡ chữ → không đoán bừa."""
    assert ai_service._heading_level(0, 12) == 0
    assert ai_service._heading_level(12, 0) == 0


# --- gom dòng thành đoạn ---------------------------------------------------


def test_wrapped_line_is_joined_into_the_open_paragraph():
    """Dòng chạm mép phải cột là chữ tự xuống dòng → nối vào đoạn đang mở."""
    lines = [
        _line("Trong moi truong truyen thong so phat trien voi toc do", right=500.0, top=700.0),
        _line("chong mat hien nay, nguoi sang tao noi dung phai doi mat", right=500.0, top=686.0),
        _line("voi nhung thach thuc lon.", right=300.0, top=672.0),
    ]

    markdown = ai_service._lines_to_markdown(lines, 12.0)

    assert markdown == (
        "Trong moi truong truyen thong so phat trien voi toc do "
        "chong mat hien nay, nguoi sang tao noi dung phai doi mat "
        "voi nhung thach thuc lon."
    )


def test_line_that_stops_short_of_the_column_starts_a_new_paragraph():
    """Dòng trước kết thúc giữa cột (câu đã hết) → dòng sau là đoạn khác."""
    lines = [
        _line("Mot cau ngan.", right=200.0, top=700.0),
        _line("Mot cau khac cung ngan.", right=250.0, top=686.0),
    ]

    assert ai_service._lines_to_markdown(lines, 12.0) == (
        "Mot cau ngan.\nMot cau khac cung ngan."
    )


def test_large_vertical_gap_starts_a_new_paragraph():
    """Cách dòng lớn hơn nhịp thường → đoạn mới dù dòng trước chạm mép cột."""
    lines = [
        _line("Dong mo ta mot y trong tai lieu.", right=500.0, top=700.0),
        _line("Dong tiep theo noi tiep cau dang do.", right=500.0, top=686.0),
        _line("Doan thu hai cach mot khoang lon.", right=500.0, top=650.0),
    ]

    markdown = ai_service._lines_to_markdown(lines, 12.0)

    assert markdown.split("\n") == [
        "Dong mo ta mot y trong tai lieu. Dong tiep theo noi tiep cau dang do.",
        "Doan thu hai cach mot khoang lon.",
    ]


def test_hyphenated_line_is_joined_without_space():
    """Từ bị ngắt bằng gạch nối cuối dòng nối liền, giữ gạch nối."""
    lines = [
        _line("nguyen ly Bien tap video phi tuyen tinh (Non-", right=500.0, top=700.0),
        _line("Linear Editing - NLE).", right=300.0, top=686.0),
    ]

    assert ai_service._lines_to_markdown(lines, 12.0) == (
        "nguyen ly Bien tap video phi tuyen tinh (Non-Linear Editing - NLE)."
    )


def test_bullet_item_keeps_its_wrapped_lines():
    """Gạch đầu dòng bị ngắt sang dòng sau vẫn là một đoạn."""
    lines = [
        _line("- Thu thap va phan tich yeu cau tu nhom nguoi dung", right=500.0, top=700.0),
        _line("muc tieu cua du an.", right=300.0, top=686.0),
        _line("- Thuc hien khao sat nguoi dung.", right=300.0, top=672.0),
    ]

    markdown = ai_service._lines_to_markdown(lines, 12.0)

    assert markdown.split("\n") == [
        "- Thu thap va phan tich yeu cau tu nhom nguoi dung muc tieu cua du an.",
        "- Thuc hien khao sat nguoi dung.",
    ]


# --- gạch đầu dòng vẽ riêng ------------------------------------------------


def test_bullet_marker_line_is_attached_to_its_text():
    """Dấu "•" vẽ bằng lượt chữ riêng bị tách dòng → gắn về đầu dòng chữ của nó."""
    lines = [
        _line("Role: Team Leader | Team size: 6", left=221.6, top=493.9, right=438.0),
        _line("Led a 6-member team to deliver the project on schedule.", left=221.6, top=455.0),
        _line("•", left=226.6, top=455.4, right=228.9),
    ]

    markdown = ai_service._lines_to_markdown(lines, 12.0)

    assert markdown.split("\n") == [
        "Role: Team Leader | Team size: 6",
        "• Led a 6-member team to deliver the project on schedule.",
    ]


def test_bullet_marker_is_not_attached_across_columns():
    """Dấu ở cột phải không được gắn vào dòng cùng độ cao ở cột trái."""
    lines = [
        _line("Problem Solving", left=49.7, top=442.7, right=114.9),
        _line("•", left=226.6, top=442.5, right=228.9),
        _line("Designed test scenarios for the app.", left=221.6, top=442.9),
    ]

    markdown = ai_service._lines_to_markdown(lines, 12.0)

    assert markdown.split("\n") == [
        "Problem Solving",
        "• Designed test scenarios for the app.",
    ]


# --- dấu cách dựng lại từ toạ độ -------------------------------------------


def test_missing_space_is_rebuilt_from_character_positions():
    """pdfium bỏ mất dấu cách khi nó được đặt bằng dịch con trỏ → phải dựng lại.

    "Mot" vẽ ở x=72 rộng ~21pt, "hai" vẽ ở x=100 (khe hở ~6pt ≈ 0.5 cỡ chữ) →
    chắc chắn là hai từ.
    """
    content = (
        b"BT /F1 12 Tf 72 700 Td (Mot) Tj ET\n"
        b"BT /F1 12 Tf 100 700 Td (hai) Tj ET\n"
    )

    pages = ai_service.extract_pdf_pages_markdown(_build_pdf_raw(content))

    assert pages[0].strip() == "Mot hai"


def test_character_spacing_inside_a_word_does_not_add_spaces():
    """Chữ trong cùng một từ (khe hở ~1pt) không được chèn dấu cách."""
    content = (
        b"BT /F1 12 Tf 72 700 Td (M) Tj ET\n"
        b"BT /F1 12 Tf 81 700 Td (ot) Tj ET\n"
    )

    pages = ai_service.extract_pdf_pages_markdown(_build_pdf_raw(content))

    assert pages[0].strip() == "Mot"


# --- đường cũ vẫn chạy -----------------------------------------------------


def test_single_page_text_layer_still_readable_by_ocr():
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
