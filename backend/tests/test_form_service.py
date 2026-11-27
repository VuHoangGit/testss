import io
import zipfile

import pymupdf
from docx import Document
from PIL import Image

from app.services import form_service


def _logo_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGBA", (240, 80), (30, 100, 220, 255)).save(buffer, format="PNG")
    return buffer.getvalue()


def test_list_templates_only_supported_files(tmp_path):
    (tmp_path / "a.pdf").write_bytes(b"%PDF")
    (tmp_path / "b.docx").write_bytes(b"docx")
    (tmp_path / "c.doc").write_bytes(b"doc")
    (tmp_path / "skip.txt").write_text("skip", encoding="utf-8")

    items = form_service.list_templates(str(tmp_path))
    assert [item["name"] for item in items] == ["a.pdf", "b.docx", "c.doc"]


def test_pdf_template_receives_scaled_logo(tmp_path):
    source = tmp_path / "form.pdf"
    pdf = pymupdf.open()
    page = pdf.new_page(width=595, height=842)
    page.insert_text((72, 72), "Biểu mẫu thử nghiệm")
    pdf.save(source)
    pdf.close()

    result, name, mime = form_service.process_template(
        configured_dir=str(tmp_path),
        template_name=source.name,
        logo_bytes=_logo_bytes(),
    )

    assert name == "form-logo.pdf"
    assert mime == "application/pdf"
    with pymupdf.open(stream=result, filetype="pdf") as opened:
        assert opened.page_count == 1
        assert len(opened[0].get_images(full=True)) >= 1


def test_pdf_template_receives_logo_on_every_page(tmp_path):
    source = tmp_path / "form-multi.pdf"
    pdf = pymupdf.open()
    pdf.new_page(width=595, height=842)
    pdf.new_page(width=595, height=842)
    pdf.save(source)
    pdf.close()

    result, _, mime = form_service.process_template(
        configured_dir=str(tmp_path),
        template_name=source.name,
        logo_bytes=_logo_bytes(),
    )

    assert mime == "application/pdf"
    with pymupdf.open(stream=result, filetype="pdf") as opened:
        assert opened.page_count == 2
        assert all(len(page.get_images(full=True)) >= 1 for page in opened)


def test_docx_template_has_logo_in_header(tmp_path):
    source = tmp_path / "form.docx"
    document = Document()
    document.add_heading("Biểu mẫu", level=1)
    document.add_paragraph("Nội dung.")
    document.save(source)

    result, name, mime = form_service.process_template(
        configured_dir=str(tmp_path),
        template_name=source.name,
        logo_bytes=_logo_bytes(),
    )

    assert name == "form-logo.docx"
    assert mime.endswith("wordprocessingml.document")
    reopened = Document(io.BytesIO(result))
    assert reopened.paragraphs[0].text == "Biểu mẫu"
    assert "w:drawing" in reopened.sections[0].header._element.xml


def test_pdf_template_supports_position_watermark_and_password(tmp_path):
    source = tmp_path / "form.pdf"
    pdf = pymupdf.open()
    pdf.new_page(width=595, height=842)
    pdf.save(source)
    pdf.close()

    result, name, _ = form_service.process_template(
        configured_dir=str(tmp_path),
        template_name=source.name,
        logo_bytes=_logo_bytes(),
        x=0.25,
        y=0.60,
        is_watermark=True,
        password="khachhang",
    )

    assert name == "form-logo.pdf"
    with pymupdf.open(stream=result, filetype="pdf") as opened:
        assert opened.is_encrypted


def test_create_output_zip_contains_all_templates(tmp_path):
    (tmp_path / "first.pdf").write_bytes(b"%PDF")
    pdf = pymupdf.open()
    pdf.new_page(width=595, height=842)
    pdf.save(tmp_path / "first.pdf")
    pdf.close()

    pdf = pymupdf.open()
    pdf.new_page(width=595, height=842)
    pdf.save(tmp_path / "second.pdf")
    pdf.close()

    zip_bytes, zip_name = form_service.create_output_zip(
        configured_dir=str(tmp_path),
        template_names=["first.pdf", "second.pdf"],
        logo_bytes=_logo_bytes(),
    )

    assert zip_name == "processed-forms.zip"
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as archive:
        assert set(archive.namelist()) == {"first-logo.pdf", "second-logo.pdf"}


def test_pdf_template_supports_multiple_logo_placements(tmp_path):
    source = tmp_path / "form-multi-logo.pdf"
    pdf = pymupdf.open()
    pdf.new_page(width=595, height=842)
    pdf.save(source)
    pdf.close()

    result, _, _ = form_service.process_template(
        configured_dir=str(tmp_path),
        template_name=source.name,
        logo_bytes=_logo_bytes(),
        logo_placements=[
            (_logo_bytes(), 0.10, 0.10),
            (_logo_bytes(), 0.70, 0.70),
        ],
    )

    with pymupdf.open(stream=result, filetype="pdf") as opened:
        assert len(opened[0].get_images(full=True)) >= 2


def test_render_page_png_contains_document_content(tmp_path):
    source = tmp_path / "preview.pdf"
    pdf = pymupdf.open()
    page = pdf.new_page(width=595, height=842)
    page.insert_text((72, 120), "VISIBLE DOCUMENT CONTENT")
    pdf.save(source)
    pdf.close()

    png, page_count, width, height = form_service.render_page_png(
        configured_dir=str(tmp_path),
        template_name=source.name,
    )

    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    assert page_count == 1
    assert width == 595
    assert height == 842
    rendered = Image.open(io.BytesIO(png)).convert("RGB")
    non_white_pixels = sum(1 for pixel in rendered.getdata() if pixel != (255, 255, 255))
    assert non_white_pixels > 100


def test_pdf_logo_placement_uses_dragged_size(tmp_path):
    """Placement 5 phần tử (x, y, w, h) phải đóng dấu đúng rect đã kéo trên preview."""
    source = tmp_path / "form-wysiwyg.pdf"
    pdf = pymupdf.open()
    pdf.new_page(width=595, height=842)
    pdf.save(source)
    pdf.close()

    result, _, _ = form_service.process_template(
        configured_dir=str(tmp_path),
        template_name=source.name,
        logo_bytes=_logo_bytes(),
        logo_placements=[(_logo_bytes(), 0.30, 0.20, 0.25, 0.12)],
    )

    with pymupdf.open(stream=result, filetype="pdf") as opened:
        page = opened[0]
        images = page.get_images(full=True)
        assert len(images) == 1
        rects = page.get_image_rects(images[0][0])
        assert len(rects) == 1
        rect = rects[0]
        # Logo 240x80 trong hộp (0.25*595) x (0.12*842): BoxFit.contain →
        # hiển thị 148.75 x 49.58, căn giữa trong hộp.
        box_w, box_h = 0.25 * 595, 0.12 * 842
        scale = min(box_w / 240, box_h / 80)
        disp_w, disp_h = 240 * scale, 80 * scale
        dx = (box_w - disp_w) / 2
        dy = (box_h - disp_h) / 2
        assert abs(rect.width - disp_w) < 1.0
        assert abs(rect.height - disp_h) < 1.0
        assert abs(rect.x0 - (0.30 * 595 + dx)) < 1.0
        assert abs(rect.y0 - (0.20 * 842 + dy)) < 1.0


def test_render_page_png_first_page(tmp_path):
    source = tmp_path / "form.pdf"
    pdf = pymupdf.open()
    page = pdf.new_page(width=595, height=842)
    page.insert_text((72, 72), "Trang 1")
    pdf.new_page(width=595, height=842)
    pdf.save(source)
    pdf.close()

    png, page_count, page_width, page_height = form_service.render_page_png(
        str(tmp_path), source.name, page_number=0
    )

    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    assert page_count == 2
    assert abs(page_width - 595.0) < 1.0
    assert abs(page_height - 842.0) < 1.0
    image = Image.open(io.BytesIO(png))
    assert image.width == int(595 * 2)
    assert image.height == int(842 * 2)


def test_render_page_png_second_page_and_invalid(tmp_path):
    source = tmp_path / "multi.pdf"
    pdf = pymupdf.open()
    pdf.new_page(width=595, height=842)
    pdf.new_page(width=595, height=842)
    pdf.save(source)
    pdf.close()

    png, page_count, _, _ = form_service.render_page_png(str(tmp_path), source.name, page_number=1)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    assert page_count == 2

    try:
        form_service.render_page_png(str(tmp_path), source.name, page_number=5)
    except ValueError:
        pass
    else:
        raise AssertionError("page_number ngoài phạm vi phải raise ValueError")


# ---------------------------------------------------------------------------
# Tệp người dùng tự đính kèm (không nằm trong form_templates/)
# ---------------------------------------------------------------------------


def _pdf_bytes(pages: int = 1) -> bytes:
    pdf = pymupdf.open()
    for _ in range(pages):
        pdf.new_page(width=595, height=842)
    data = pdf.tobytes()
    pdf.close()
    return data


def _docx_bytes() -> bytes:
    document = Document()
    document.add_heading("Biểu mẫu người dùng", level=1)
    document.add_paragraph("Nội dung do người dùng tải lên.")
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def test_sanitize_upload_name_strips_traversal_and_bad_chars(tmp_path):
    assert form_service.sanitize_upload_name("../../etc/passwd.pdf") == "passwd.pdf"
    windows_path = r"C:\Users\a\Báo cáo.docx"
    assert form_service.sanitize_upload_name(windows_path) == "Báo cáo.docx"
    assert form_service.sanitize_upload_name("a:b?.pdf") == "a_b_.pdf"
    assert form_service.sanitize_upload_name("....pdf") == "bieu-mau.pdf"


def test_sanitize_upload_name_rejects_unsupported():
    for bad in ("", None, "..", "note.txt", "script.exe"):
        try:
            form_service.sanitize_upload_name(bad)
        except ValueError:
            continue
        raise AssertionError(f"Phải từ chối tên {bad!r}")


def test_validate_upload_rejects_wrong_magic():
    try:
        form_service.validate_upload("fake.pdf", b"khong phai pdf")
    except ValueError:
        pass
    else:
        raise AssertionError("PDF sai chữ ký phải raise ValueError")

    try:
        form_service.validate_upload("fake.docx", b"khong phai zip")
    except ValueError:
        pass
    else:
        raise AssertionError("DOCX sai chữ ký phải raise ValueError")

    try:
        form_service.validate_upload("empty.pdf", b"")
    except ValueError:
        pass
    else:
        raise AssertionError("Tệp rỗng phải raise ValueError")


def test_process_uploaded_pdf_template_receives_logo(tmp_path):
    result, name, mime = form_service.process_uploaded_template(
        file_name="hopdong.pdf",
        file_bytes=_pdf_bytes(2),
        logo_bytes=_logo_bytes(),
    )

    assert name == "hopdong-logo.pdf"
    assert mime == "application/pdf"
    with pymupdf.open(stream=result, filetype="pdf") as opened:
        assert opened.page_count == 2
        assert all(len(page.get_images(full=True)) >= 1 for page in opened)


def test_process_uploaded_docx_template_has_logo_in_header():
    result, name, mime = form_service.process_uploaded_template(
        file_name="donxin.docx",
        file_bytes=_docx_bytes(),
        logo_bytes=_logo_bytes(),
    )

    assert name == "donxin-logo.docx"
    assert mime.endswith("wordprocessingml.document")
    reopened = Document(io.BytesIO(result))
    assert "w:drawing" in reopened.sections[0].header._element.xml


def test_create_output_zip_accepts_uploaded_templates(tmp_path):
    pdf = pymupdf.open()
    pdf.new_page(width=595, height=842)
    pdf.save(tmp_path / "co-san.pdf")
    pdf.close()

    zip_bytes, _ = form_service.create_output_zip(
        configured_dir=str(tmp_path),
        template_names=["co-san.pdf"],
        logo_bytes=_logo_bytes(),
        uploaded_templates=[("nguoi-dung.pdf", _pdf_bytes())],
    )

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as archive:
        assert set(archive.namelist()) == {"co-san-logo.pdf", "nguoi-dung-logo.pdf"}


def test_create_output_zip_dedupes_same_output_name(tmp_path):
    zip_bytes, _ = form_service.create_output_zip(
        configured_dir=str(tmp_path),
        template_names=[],
        logo_bytes=_logo_bytes(),
        uploaded_templates=[
            ("trung.pdf", _pdf_bytes()),
            ("trung.pdf", _pdf_bytes()),
        ],
    )

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as archive:
        assert set(archive.namelist()) == {"trung-logo.pdf", "trung-logo-2.pdf"}


def test_create_output_zip_requires_at_least_one_template(tmp_path):
    try:
        form_service.create_output_zip(
            configured_dir=str(tmp_path),
            template_names=[],
            logo_bytes=_logo_bytes(),
        )
    except ValueError:
        pass
    else:
        raise AssertionError("Không có biểu mẫu nào phải raise ValueError")


def test_render_uploaded_page_png():
    png, page_count, width, height = form_service.render_uploaded_page_png(
        "xem-truoc.pdf",
        _pdf_bytes(3),
        page_number=1,
    )

    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    assert page_count == 3
    assert abs(width - 595.0) < 1.0
    assert abs(height - 842.0) < 1.0


def test_render_uploaded_page_png_rejects_bad_page():
    try:
        form_service.render_uploaded_page_png("a.pdf", _pdf_bytes(1), page_number=9)
    except ValueError:
        pass
    else:
        raise AssertionError("Số trang ngoài phạm vi phải raise ValueError")


# ---------------------------------------------------------------------------
# Chọn định dạng xuất (PDF hoặc Word)
# ---------------------------------------------------------------------------


def test_normalize_output_format():
    assert form_service.normalize_output_format(None) is None
    assert form_service.normalize_output_format("  ") is None
    assert form_service.normalize_output_format("PDF") == "pdf"
    assert form_service.normalize_output_format("word") == "docx"
    try:
        form_service.normalize_output_format("excel")
    except ValueError:
        pass
    else:
        raise AssertionError("Định dạng lạ phải raise ValueError")


def test_pdf_template_can_export_to_docx(tmp_path):
    pdf = pymupdf.open()
    page = pdf.new_page(width=595, height=842)
    page.insert_text((72, 100), "NOI DUNG XUAT WORD")
    pdf.save(tmp_path / "goc.pdf")
    pdf.close()

    result, name, mime = form_service.process_template(
        configured_dir=str(tmp_path),
        template_name="goc.pdf",
        logo_bytes=_logo_bytes(),
        output_format="docx",
    )

    assert name == "goc-logo.docx"
    assert mime.endswith("wordprocessingml.document")
    reopened = Document(io.BytesIO(result))
    assert "w:drawing" in reopened.sections[0].header._element.xml


def test_docx_output_rejects_password(tmp_path):
    pdf = pymupdf.open()
    pdf.new_page(width=595, height=842)
    pdf.save(tmp_path / "goc.pdf")
    pdf.close()

    try:
        form_service.process_template(
            configured_dir=str(tmp_path),
            template_name="goc.pdf",
            logo_bytes=_logo_bytes(),
            output_format="docx",
            password="bi-mat",
        )
    except ValueError:
        pass
    else:
        raise AssertionError("Mật khẩu + xuất Word phải raise ValueError")
