"""Test API biểu mẫu: tệp có sẵn + tệp người dùng đính kèm + chọn định dạng xuất."""

import io
import zipfile

import pymupdf
import pytest
from PIL import Image

from app.core.config import get_settings


def _pdf_bytes(pages: int = 1) -> bytes:
    pdf = pymupdf.open()
    for _ in range(pages):
        pdf.new_page(width=595, height=842)
    data = pdf.tobytes()
    pdf.close()
    return data


def _logo_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGBA", (240, 80), (30, 100, 220, 255)).save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.fixture()
def auth_headers(make_token):
    token = make_token(sub="sub-forms", email="forms@gmail.com", name="Forms")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def templates_dir(tmp_path, monkeypatch):
    """Trỏ thư mục biểu mẫu vào tmp để test không đụng form_templates/ thật."""
    settings = get_settings().model_copy(
        update={"form_templates_dir": str(tmp_path)},
    )
    monkeypatch.setattr("app.api.v1.forms.get_settings", lambda: settings)
    return tmp_path


def test_templates_requires_auth(client, templates_dir):
    resp = client.get("/api/v1/forms/templates")
    assert resp.status_code in (401, 403)


def test_templates_lists_supported_files(client, auth_headers, templates_dir):
    (templates_dir / "mau.pdf").write_bytes(_pdf_bytes())
    (templates_dir / "ghi-chu.txt").write_text("bo qua", encoding="utf-8")

    resp = client.get("/api/v1/forms/templates", headers=auth_headers)

    assert resp.status_code == 200
    names = [item["name"] for item in resp.json()]
    assert names == ["mau.pdf"]


def test_preview_upload_returns_png_with_page_headers(client, auth_headers, templates_dir):
    resp = client.post(
        "/api/v1/forms/preview-upload?page=0",
        headers=auth_headers,
        files={"file": ("hopdong.pdf", _pdf_bytes(2), "application/pdf")},
    )

    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/png"
    assert resp.headers["x-page-count"] == "2"
    assert float(resp.headers["x-page-width-pt"]) == pytest.approx(595.0)
    assert float(resp.headers["x-page-height-pt"]) == pytest.approx(842.0)
    assert resp.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_preview_upload_rejects_unsupported_extension(client, auth_headers, templates_dir):
    resp = client.post(
        "/api/v1/forms/preview-upload",
        headers=auth_headers,
        files={"file": ("note.txt", b"noi dung", "text/plain")},
    )

    assert resp.status_code == 422


def test_preview_upload_rejects_fake_pdf(client, auth_headers, templates_dir):
    resp = client.post(
        "/api/v1/forms/preview-upload",
        headers=auth_headers,
        files={"file": ("gia.pdf", b"khong phai pdf", "application/pdf")},
    )

    assert resp.status_code == 422


def test_process_with_uploaded_template_only(client, auth_headers, templates_dir):
    resp = client.post(
        "/api/v1/forms/process",
        headers=auth_headers,
        files=[
            ("logos", ("logo.png", _logo_bytes(), "image/png")),
            ("template_files", ("hopdong.pdf", _pdf_bytes(2), "application/pdf")),
        ],
        data={"is_watermark": "false"},
    )

    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"] == "application/zip"
    assert "processed-forms.zip" in resp.headers["content-disposition"]
    with zipfile.ZipFile(io.BytesIO(resp.content)) as archive:
        assert archive.namelist() == ["hopdong-logo.pdf"]
        output = archive.read("hopdong-logo.pdf")
    with pymupdf.open(stream=output, filetype="pdf") as opened:
        assert opened.page_count == 2
        assert all(len(page.get_images(full=True)) >= 1 for page in opened)


def test_process_combines_server_and_uploaded_templates(client, auth_headers, templates_dir):
    (templates_dir / "co-san.pdf").write_bytes(_pdf_bytes())

    resp = client.post(
        "/api/v1/forms/process",
        headers=auth_headers,
        files=[
            ("logos", ("logo.png", _logo_bytes(), "image/png")),
            ("template_files", ("cua-toi.pdf", _pdf_bytes(), "application/pdf")),
        ],
        data={"template_names": "co-san.pdf", "is_watermark": "false"},
    )

    assert resp.status_code == 200, resp.text
    with zipfile.ZipFile(io.BytesIO(resp.content)) as archive:
        assert set(archive.namelist()) == {"co-san-logo.pdf", "cua-toi-logo.pdf"}


def test_process_requires_some_template(client, auth_headers, templates_dir):
    resp = client.post(
        "/api/v1/forms/process",
        headers=auth_headers,
        files=[("logos", ("logo.png", _logo_bytes(), "image/png"))],
        data={"is_watermark": "false"},
    )

    assert resp.status_code == 422
    assert "biểu mẫu" in resp.json()["detail"]


def test_process_rejects_unknown_output_format(client, auth_headers, templates_dir):
    resp = client.post(
        "/api/v1/forms/process",
        headers=auth_headers,
        files=[
            ("logos", ("logo.png", _logo_bytes(), "image/png")),
            ("template_files", ("hopdong.pdf", _pdf_bytes(), "application/pdf")),
        ],
        data={"output_format": "excel", "is_watermark": "false"},
    )

    assert resp.status_code == 422
    assert "PDF hoặc DOCX" in resp.json()["detail"]


def test_process_exports_pdf_template_to_docx(client, auth_headers, templates_dir):
    resp = client.post(
        "/api/v1/forms/process",
        headers=auth_headers,
        files=[
            ("logos", ("logo.png", _logo_bytes(), "image/png")),
            ("template_files", ("hopdong.pdf", _pdf_bytes(), "application/pdf")),
        ],
        data={"output_format": "docx", "is_watermark": "false"},
    )

    assert resp.status_code == 200, resp.text
    with zipfile.ZipFile(io.BytesIO(resp.content)) as archive:
        assert archive.namelist() == ["hopdong-logo.docx"]
        assert archive.read("hopdong-logo.docx").startswith(b"PK")
