"""Test API folders/documents + PDF tools (Sprint 2). Đăng nhập qua dev-login."""

import io

import pytest
from pypdf import PdfReader, PdfWriter

from app.core.config import get_settings


def make_pdf(pages: int) -> bytes:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=200, height=200)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


@pytest.fixture()
def auth_headers(client, monkeypatch):
    """Bật dev-login + đăng nhập user chính, trả Authorization headers."""
    monkeypatch.setattr(get_settings(), "allow_dev_login", True)
    resp = client.post("/api/v1/auth/dev", json={"email": "owner@gmail.com", "name": "Owner"})
    assert resp.status_code == 200, resp.text
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def other_headers(client, monkeypatch):
    """User thứ 2 để test phân quyền (isolation giữa owner)."""
    resp = client.post("/api/v1/auth/dev", json={"email": "other@gmail.com", "name": "Other"})
    assert resp.status_code == 200, resp.text
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _upload(client, headers, name: str, data: bytes, folder_id=None):
    files = {"file": (name, data, "application/pdf")}
    form = {"folder_id": folder_id} if folder_id else {}
    return client.post("/api/v1/documents", headers=headers, files=files, data=form)


class TestFolders:
    def test_create_and_list(self, client, auth_headers):
        resp = client.post("/api/v1/folders", headers=auth_headers, json={"name": "Hợp đồng"})
        assert resp.status_code == 201
        folder = resp.json()
        assert folder["name"] == "Hợp đồng"

        listing = client.get("/api/v1/folders", headers=auth_headers).json()
        assert [f["name"] for f in listing] == ["Hợp đồng"]
        assert listing[0]["document_count"] == 0

    def test_delete_empty_folder(self, client, auth_headers):
        folder = client.post(
            "/api/v1/folders", headers=auth_headers, json={"name": "Trống"}
        ).json()
        resp = client.delete(f"/api/v1/folders/{folder['id']}", headers=auth_headers)
        assert resp.status_code == 200
        assert client.get("/api/v1/folders", headers=auth_headers).json() == []

    def test_delete_folder_with_documents_conflict(self, client, auth_headers):
        folder = client.post(
            "/api/v1/folders", headers=auth_headers, json={"name": "Có file"}
        ).json()
        _upload(client, auth_headers, "a.pdf", make_pdf(1), folder_id=folder["id"])
        resp = client.delete(f"/api/v1/folders/{folder['id']}", headers=auth_headers)
        assert resp.status_code == 409

    def test_folder_of_other_user_invisible(self, client, auth_headers, other_headers):
        client.post("/api/v1/folders", headers=auth_headers, json={"name": "Của tôi"})
        assert client.get("/api/v1/folders", headers=other_headers).json() == []


class TestUploadListDownload:
    def test_upload_pdf_records_page_count(self, client, auth_headers):
        resp = _upload(client, auth_headers, "ba_page.pdf", make_pdf(3))
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["original_name"] == "ba_page.pdf"
        assert body["page_count"] == 3
        assert body["size_bytes"] > 0
        assert body["mime_type"] == "application/pdf"

    def test_upload_empty_file_rejected(self, client, auth_headers):
        resp = _upload(client, auth_headers, "rong.pdf", b"")
        assert resp.status_code == 400

    def test_upload_into_folder_and_filter(self, client, auth_headers):
        folder = client.post(
            "/api/v1/folders", headers=auth_headers, json={"name": "F1"}
        ).json()
        _upload(client, auth_headers, "in.pdf", make_pdf(1), folder_id=folder["id"])
        _upload(client, auth_headers, "out.pdf", make_pdf(1))

        in_folder = client.get(
            "/api/v1/documents", headers=auth_headers, params={"folder_id": folder["id"]}
        ).json()
        assert [d["original_name"] for d in in_folder] == ["in.pdf"]

        all_docs = client.get("/api/v1/documents", headers=auth_headers).json()
        assert len(all_docs) == 2

    def test_upload_to_missing_folder_404(self, client, auth_headers):
        import uuid as uuid_mod

        resp = _upload(client, auth_headers, "x.pdf", make_pdf(1), folder_id=str(uuid_mod.uuid4()))
        assert resp.status_code == 404

    def test_download_roundtrip(self, client, auth_headers):
        data = make_pdf(2)
        doc = _upload(client, auth_headers, "tai-lieu.pdf", data).json()
        resp = client.get(f"/api/v1/documents/{doc['id']}/download", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.content == data
        assert "tai-lieu" in resp.headers.get("content-disposition", "")

    def test_delete_document_removes_file(self, client, auth_headers):
        doc = _upload(client, auth_headers, "xoa.pdf", make_pdf(1)).json()
        resp = client.delete(f"/api/v1/documents/{doc['id']}", headers=auth_headers)
        assert resp.status_code == 200
        assert client.get("/api/v1/documents", headers=auth_headers).json() == []
        storage = get_settings().documents_dir
        import pathlib

        assert list(pathlib.Path(storage).glob("*.pdf")) == []


class TestPdfTools:
    def test_merge_creates_new_document_keeps_originals(self, client, auth_headers):
        d1 = _upload(client, auth_headers, "p1.pdf", make_pdf(2)).json()
        d2 = _upload(client, auth_headers, "p2.pdf", make_pdf(3)).json()
        resp = client.post(
            "/api/v1/documents/merge",
            headers=auth_headers,
            json={"document_ids": [d1["id"], d2["id"]], "name": "Gộp lại"},
        )
        assert resp.status_code == 201, resp.text
        merged = resp.json()
        assert merged["original_name"] == "Gộp lại.pdf"
        assert merged["page_count"] == 5

        all_docs = client.get("/api/v1/documents", headers=auth_headers).json()
        assert len(all_docs) == 3  # 2 bản gốc + bản gộp

    def test_merge_requires_at_least_two(self, client, auth_headers):
        resp = client.post(
            "/api/v1/documents/merge", headers=auth_headers,
            json={"document_ids": [], "name": "x"},
        )
        assert resp.status_code == 422

    def test_merge_rejects_non_pdf(self, client, auth_headers):
        d1 = _upload(client, auth_headers, "a.pdf", make_pdf(1)).json()
        files = {"file": ("anh.png", b"\x89PNG-rac", "image/png")}
        doc_png = client.post("/api/v1/documents", headers=auth_headers, files=files).json()
        resp = client.post(
            "/api/v1/documents/merge",
            headers=auth_headers,
            json={"document_ids": [d1["id"], doc_png["id"]], "name": "x"},
        )
        assert resp.status_code == 400

    def test_split_ranges(self, client, auth_headers):
        doc = _upload(client, auth_headers, "goc.pdf", make_pdf(4)).json()
        resp = client.post(
            f"/api/v1/documents/{doc['id']}/split",
            headers=auth_headers,
            json={"ranges": "1-2,4"},
        )
        assert resp.status_code == 201, resp.text
        parts = resp.json()
        assert [p["page_count"] for p in parts] == [2, 1]
        assert parts[0]["original_name"] == "goc (trang 1-2).pdf"
        assert parts[1]["original_name"] == "goc (trang 4).pdf"

    def test_split_invalid_range_400(self, client, auth_headers):
        doc = _upload(client, auth_headers, "goc.pdf", make_pdf(2)).json()
        resp = client.post(
            f"/api/v1/documents/{doc['id']}/split",
            headers=auth_headers,
            json={"ranges": "5-9"},
        )
        assert resp.status_code == 400

    def test_protect_and_unprotect_roundtrip(self, client, auth_headers):
        doc = _upload(client, auth_headers, "baomat.pdf", make_pdf(2)).json()

        locked_resp = client.post(
            f"/api/v1/documents/{doc['id']}/protect",
            headers=auth_headers, json={"password": "mk123"},
        )
        assert locked_resp.status_code == 201, locked_resp.text
        locked = locked_resp.json()
        assert locked["original_name"] == "baomat (mat-khau).pdf"

        downloaded = client.get(
            f"/api/v1/documents/{locked['id']}/download", headers=auth_headers
        )
        assert PdfReader(io.BytesIO(downloaded.content)).is_encrypted

        unlocked_resp = client.post(
            f"/api/v1/documents/{locked['id']}/unprotect",
            headers=auth_headers, json={"password": "mk123"},
        )
        assert unlocked_resp.status_code == 201
        unlocked = unlocked_resp.json()
        assert unlocked["page_count"] == 2

    def test_unprotect_wrong_password_400(self, client, auth_headers):
        doc = _upload(client, auth_headers, "bm.pdf", make_pdf(1)).json()
        locked = client.post(
            f"/api/v1/documents/{doc['id']}/protect",
            headers=auth_headers, json={"password": "mk123"},
        ).json()
        resp = client.post(
            f"/api/v1/documents/{locked['id']}/unprotect",
            headers=auth_headers, json={"password": "sai"},
        )
        assert resp.status_code == 400

    def test_isolation_other_user_cannot_access(self, client, auth_headers, other_headers):
        doc = _upload(client, auth_headers, "rieng.pdf", make_pdf(1)).json()
        assert (
            client.get(f"/api/v1/documents/{doc['id']}/download", headers=other_headers).status_code
            == 404
        )
        assert (
            client.delete(f"/api/v1/documents/{doc['id']}", headers=other_headers).status_code
            == 404
        )
        resp = client.post(
            f"/api/v1/documents/{doc['id']}/split", headers=other_headers,
            json={"ranges": "1"},
        )
        assert resp.status_code == 404

    def test_download_missing_document_404(self, client, auth_headers):
        import uuid as uuid_mod

        resp = client.get(
            f"/api/v1/documents/{uuid_mod.uuid4()}/download", headers=auth_headers
        )
        assert resp.status_code == 404
