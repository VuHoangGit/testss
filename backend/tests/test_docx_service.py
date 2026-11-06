"""Test xuất Word: giữ outline level (heading), bảng, danh sách, TOC, số trang."""

import io

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn

from app.services import docx_service


def _document(text: str, *, include_toc: bool = True, title: str | None = None) -> Document:
    return docx_service.build_document(text, include_toc=include_toc, title=title)


def _styles(document: Document) -> list[str]:
    return [paragraph.style.name for paragraph in document.paragraphs]


# ---------------------------------------------------------------------------
# Heading → outline level (thứ quyết định mục lục)


def test_heading_levels_become_word_heading_styles():
    document = _document(
        "# Chương 1. Tổng quan\n## 1.1 Phạm vi\n### 1.1.1 Chi tiết\nNội dung thường.\n",
        include_toc=False,
    )

    styles = _styles(document)
    assert "Heading 1" in styles
    assert "Heading 2" in styles
    assert "Heading 3" in styles
    # chữ đã bỏ dấu # và giữ nguyên nội dung
    headings = [p.text for p in document.paragraphs if p.style.name.startswith("Heading")]
    assert headings == ["Chương 1. Tổng quan", "1.1 Phạm vi", "1.1.1 Chi tiết"]


def test_heading_without_space_after_hashes_is_still_heading():
    document = _document("##1.1 Phạm vi\n", include_toc=False)
    assert document.paragraphs[0].style.name == "Heading 2"
    assert document.paragraphs[0].text == "1.1 Phạm vi"


def test_heading_keeps_inline_bold_run():
    document = _document("## Điều **5** quan trọng\n", include_toc=False)
    paragraph = document.paragraphs[0]
    assert paragraph.style.name == "Heading 2"
    assert paragraph.text == "Điều 5 quan trọng"
    assert any(run.bold for run in paragraph.runs if run.text == "5")


def test_plain_text_without_markup_stays_normal_paragraph():
    document = _document("Chỉ là một câu văn bình thường.\n", include_toc=False)
    assert _styles(document)[0] == "Normal"
    assert document.paragraphs[0].text == "Chỉ là một câu văn bình thường."


def test_no_heading_means_no_table_of_contents():
    document = _document("Một dòng.\nHai dòng.\n")
    xml = document.element.xml
    assert "TOC \\o" not in xml
    assert "Mục lục" not in [p.text for p in document.paragraphs]


def test_two_headings_add_toc_and_page_break():
    document = _document("# Một\nNội dung.\n## Hai\nNội dung.\n")

    xml = document.element.xml
    assert 'TOC \\o "1-3"' in xml
    # Word phải tính lại field khi mở file, nếu không mục lục trống
    assert "updateFields" in document.settings.element.xml
    # trang mục lục tách khỏi nội dung
    assert 'w:type="page"' in xml


def test_update_fields_flag_sits_before_compat_in_settings():
    """Sai thứ tự phần tử trong settings.xml → Word báo file hỏng."""
    document = _document("# Một\n## Hai\n")

    children = [child.tag.split("}")[-1] for child in document.settings.element]
    assert children.index("updateFields") < children.index("compat")


def test_toc_field_has_full_field_structure():
    """Field phải có begin → instrText → separate → end (đúng cú pháp OOXML)."""
    document = _document("# Một\n## Hai\n")
    toc_paragraph = next(p for p in document.paragraphs if "TOC" in p._p.xml)

    marks = [mark.get(qn("w:fldCharType")) for mark in toc_paragraph._p.iter(qn("w:fldChar"))]
    assert marks == ["begin", "separate", "end"]
    assert 'TOC \\o "1-3"' in toc_paragraph._p.xml


# ---------------------------------------------------------------------------
# Bảng


def test_markdown_table_becomes_real_word_table():
    document = _document(
        "| Tên | Số tiền |\n|:---|---:|\n| Phí dịch vụ | 1.250.000 |\n| Thuế | 125.000 |\n",
        include_toc=False,
    )

    assert len(document.tables) == 1
    table = document.tables[0]
    assert table.style.name == "Table Grid"
    assert len(table.rows) == 3  # 1 header + 2 dòng dữ liệu
    assert [cell.text for cell in table.rows[0].cells] == ["Tên", "Số tiền"]
    assert [cell.text for cell in table.rows[1].cells] == ["Phí dịch vụ", "1.250.000"]
    # hàng tiêu đề in đậm + lặp lại khi sang trang
    assert all(run.bold for run in table.cell(0, 0).paragraphs[0].runs)
    assert "tblHeader" in table.rows[0]._tr.xml
    # căn lề theo :---: / ---:
    assert table.cell(1, 0).paragraphs[0].alignment == WD_ALIGN_PARAGRAPH.LEFT
    assert table.cell(1, 1).paragraphs[0].alignment == WD_ALIGN_PARAGRAPH.RIGHT
    # dấu | thô không còn trong file
    assert "|" not in table.cell(1, 0).text


def test_table_rows_with_uneven_cells_are_padded():
    document = _document("| A | B |\n|---|---|\n| chỉ một ô |\n", include_toc=False)

    table = document.tables[0]
    assert [cell.text for cell in table.rows[1].cells] == ["chỉ một ô", ""]


def test_table_with_escaped_pipe_keeps_pipe_in_cell():
    document = _document("| Ký hiệu |\n|---|\n| a \\| b |\n", include_toc=False)

    assert document.tables[0].cell(1, 0).text == "a | b"


def test_text_after_table_is_a_normal_paragraph():
    document = _document("| A |\n|---|\n| 1 |\nĐoạn sau bảng.\n", include_toc=False)

    assert document.paragraphs[-1].text == "Đoạn sau bảng."
    assert document.paragraphs[-1].style.name == "Normal"


def test_table_without_divider_row_is_still_a_table():
    """Model OCR hay bỏ dòng |---| — vẫn phải ra bảng, không phải chữ có dấu |."""
    document = _document("| Khoản | Số tiền |\n| Phí | 1.250.000 |\n", include_toc=False)

    assert len(document.tables) == 1
    table = document.tables[0]
    assert len(table.rows) == 2
    assert table.cell(1, 0).text == "Phí"
    assert "|" not in table.cell(1, 0).text


def test_single_pipe_line_stays_a_paragraph():
    document = _document("| chỉ một dòng |\nĐoạn sau.\n", include_toc=False)

    assert document.tables == []
    assert document.paragraphs[0].text == "| chỉ một dòng |"


# ---------------------------------------------------------------------------
# Danh sách, trích dẫn, caption, chú thích OCR


def test_bullet_and_numbered_lists_use_list_styles():
    document = _document(
        "- Mục một\n  - Mục con\n1. Bước một\n2. Bước hai\n",
        include_toc=False,
    )

    styles = _styles(document)
    assert "List Bullet" in styles
    assert "List Bullet 2" in styles
    assert "List Number" in styles
    assert [p.text for p in document.paragraphs][:3] == ["Mục một", "Mục con", "Bước một"]


def test_page_marker_becomes_page_break_instead_of_raw_text():
    document = _document("Trang một.\n--- Trang 2 ---\nTrang hai.\n", include_toc=False)

    texts = [p.text for p in document.paragraphs]
    assert "--- Trang 2 ---" not in texts
    assert 'w:type="page"' in document.element.xml


def test_quote_and_caption_get_their_own_styles():
    document = _document("> Trích dẫn nguyên văn\nHình 1. Sơ đồ quy trình\n", include_toc=False)

    assert document.paragraphs[0].style.name == "Quote"
    assert document.paragraphs[0].text == "Trích dẫn nguyên văn"
    assert document.paragraphs[1].style.name == "Caption"


def test_ocr_uncertain_markers_are_italic_grey():
    document = _document("Ông A ký [chữ ký tay] ngày [?] tại [mất chữ].\n", include_toc=False)

    runs = {run.text: run for run in document.paragraphs[0].runs}
    for marker in ("[chữ ký tay]", "[?]", "[mất chữ]"):
        assert marker in runs
        assert runs[marker].italic is True
        assert runs[marker].font.color.rgb is not None


def test_inline_bold_italic_and_code_become_formatted_runs():
    document = _document(
        "Chữ **đậm**, *nghiêng* và `ma_code()` trong một dòng.\n", include_toc=False
    )

    runs = {run.text: run for run in document.paragraphs[0].runs}
    assert runs["đậm"].bold is True
    assert runs["nghiêng"].italic is True
    assert runs["ma_code()"].font.name == "Consolas"
    # dấu Markdown không lọt vào file
    assert "*" not in document.paragraphs[0].text
    assert "`" not in document.paragraphs[0].text


def test_asterisk_inside_numbers_is_not_italic():
    """Số liệu dạng 5*3 / 4*2 không được biến thành chữ nghiêng."""
    document = _document("Diện tích 5*3 và 4*2 mét.\n", include_toc=False)

    paragraph = document.paragraphs[0]
    assert paragraph.text == "Diện tích 5*3 và 4*2 mét."
    assert all(run.italic is not True for run in paragraph.runs)


def test_underscore_inside_word_is_not_italic():
    document = _document("Biến snake_case_name giữ nguyên.\n", include_toc=False)

    assert document.paragraphs[0].text == "Biến snake_case_name giữ nguyên."


def test_horizontal_rule_is_dropped_but_form_fill_line_is_kept():
    document = _document("Trước.\n***\nSau.\n____\n", include_toc=False)

    texts = [paragraph.text for paragraph in document.paragraphs]
    assert "***" not in texts  # dòng kẻ phân cách: bỏ
    assert "____" in texts  # chỗ trống trong biểu mẫu: giữ


# ---------------------------------------------------------------------------
# Đoán tiêu đề cho văn bản không có marker (PDF lớp text trích bằng pypdf)


def test_legal_document_without_markup_gets_inferred_headings():
    document = _document(
        "CHƯƠNG I QUY ĐỊNH CHUNG\n"
        "Điều 1. Phạm vi điều chỉnh\n"
        "Hợp đồng này áp dụng cho các bên dưới đây.\n"
        "Điều 2. Đối tượng áp dụng\n",
        include_toc=False,
    )

    styles = _styles(document)
    assert styles[0] == "Heading 1"
    assert styles[1] == "Heading 2"
    assert styles[2] == "Normal"


def test_inference_does_not_override_model_markup():
    document = _document("## Điều 1. Phạm vi\nĐiều 2. Đối tượng áp dụng\n", include_toc=False)

    # có marker sẵn → tôn trọng model, không tự nâng dòng còn lại
    assert [p.style.name for p in document.paragraphs] == ["Heading 2", "Normal"]


# ---------------------------------------------------------------------------
# Ghi file


def test_to_docx_bytes_round_trips_with_metadata_and_page_numbers():
    from docx import Document as OpenDocument

    data = docx_service.to_docx_bytes("# Tiêu đề\nNội dung.\n", title="hop-dong.pdf")

    assert data.startswith(b"PK")  # file docx là zip
    reopened = OpenDocument(io.BytesIO(data))
    assert reopened.core_properties.title == "hop-dong.pdf"
    assert reopened.paragraphs[0].style.name == "Heading 1"
    # khổ A4 thay cho Letter mặc định
    assert round(reopened.sections[0].page_width.cm, 1) == 21.0
    # chân trang có field số trang
    footer_xml = reopened.sections[0].footer.paragraphs[0]._p.xml
    assert "PAGE" in footer_xml


def test_blank_and_whitespace_only_text_does_not_crash():
    data = docx_service.to_docx_bytes("", title=None)
    assert data.startswith(b"PK")

    reopened = Document(io.BytesIO(data))
    assert reopened.paragraphs == []
