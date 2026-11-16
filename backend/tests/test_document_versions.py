"""Test lịch sử phiên bản tài liệu: upload bản mới, list, restore, delete,
diff + quota tính cả các bản cũ."""

import io
import uuid
from unittest.mock import patch

import pytest
from pypdf import PdfWriter

from app.services import diff_service


def make_pdf(pages: int = 1) -> bytes:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=200, height=200)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def make_txt(content: str) -> bytes:
    return content.encode("utf-8")


@pytest.fixture()
def auth_headers(make_token):
    token = make_token(sub="sub-ver", email="ver@gmail.com", name="Ver")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def other_headers(make_token):
    token = make_token(sub="sub-ver-other", email="verother@gmail.com", name="Other")
    return {"Authorization": f"Bearer {token}"}


def _upload_txt(client, headers, name: str, content: str):
    return client.post(
        "/api/v1/documents",
        headers=headers,
        files={"file": (name, make_txt(content), "text/plain")},
    )


class TestUploadNewVersion:
    def test_upload_new_version_archives_current(self, client, auth_headers):
        doc = _upload_txt(client, auth_headers, "hop-dong.txt", "version 1").json()
        resp = client.post(
            f"/api/v1/documents/{doc['id']}/versions",
            headers=auth_headers,
            files={"file": ("hop-dong.txt", make_txt("version 2"), "text/plain")},
            data={"label": "client edited"},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["id"] == doc["id"]  # giữ nguyên id → UI không đổi chỗ
        assert body["size_bytes"] == len(make_txt("version 2"))

        versions = client.get(
            f"/api/v1/documents/{doc['id']}/versions", headers=auth_headers
        ).json()
        assert len(versions) == 1
        assert versions[0]["version_number"] == 1
        assert versions[0]["label"] == "client edited"

    def test_upload_rejects_different_type(self, client, auth_headers):
        doc = _upload_txt(client, auth_headers, "a.txt", "v1").json()
        resp = client.post(
            f"/api/v1/documents/{doc['id']}/versions",
            headers=auth_headers,
            files={"file": ("b.pdf", make_pdf(), "application/pdf")},
        )
        assert resp.status_code == 400

    def test_other_user_cannot_version(self, client, auth_headers, other_headers):
        doc = _upload_txt(client, auth_headers, "a.txt", "v1").json()
        resp = client.post(
            f"/api/v1/documents/{doc['id']}/versions",
            headers=other_headers,
            files={"file": ("a.txt", make_txt("v2"), "text/plain")},
        )
        assert resp.status_code == 404


class TestRestoreAndDelete:
    def test_restore_bring_back_old_content(self, client, auth_headers):
        doc = _upload_txt(client, auth_headers, "a.txt", "version 1").json()
        client.post(
            f"/api/v1/documents/{doc['id']}/versions",
            headers=auth_headers,
            files={"file": ("a.txt", make_txt("version 2"), "text/plain")},
        )
        versions = client.get(
            f"/api/v1/documents/{doc['id']}/versions", headers=auth_headers
        ).json()
        v1 = versions[0]

        resp = client.post(
            f"/api/v1/documents/{doc['id']}/versions/{v1['id']}/restore",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["size_bytes"] == len(make_txt("version 1"))

        # Sau restore: lịch sử có bản v2 cũ (đã bị thay) — nội dung hiện tại là v1.
        content = client.get(
            f"/api/v1/documents/{doc['id']}/download", headers=auth_headers
        )
        assert b"version 1" in content.content

        # Restore lần nữa không làm mất gì: v2 vẫn nằm trong lịch sử
        versions2 = client.get(
            f"/api/v1/documents/{doc['id']}/versions", headers=auth_headers
        ).json()
        assert len(versions2) == 2

    def test_delete_version_removes_it(self, client, auth_headers):
        doc = _upload_txt(client, auth_headers, "a.txt", "v1").json()
        client.post(
            f"/api/v1/documents/{doc['id']}/versions",
            headers=auth_headers,
            files={"file": ("a.txt", make_txt("v2"), "text/plain")},
        )
        versions = client.get(
            f"/api/v1/documents/{doc['id']}/versions", headers=auth_headers
        ).json()
        resp = client.delete(
            f"/api/v1/documents/{doc['id']}/versions/{versions[0]['id']}",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        remaining = client.get(
            f"/api/v1/documents/{doc['id']}/versions", headers=auth_headers
        ).json()
        assert remaining == []

    def test_delete_document_cleans_version_files(
        self, client, auth_headers, db_session_factory
    ):
        """Xóa tài liệu phải xóa luôn file các bản cũ (không rác đĩa)."""
        from sqlalchemy import select

        from app.models.document_version import DocumentVersion
        from app.services import storage_service

        doc = _upload_txt(client, auth_headers, "a.txt", "v1").json()
        client.post(
            f"/api/v1/documents/{doc['id']}/versions",
            headers=auth_headers,
            files={"file": ("a.txt", make_txt("v2"), "text/plain")},
        )

        # Lấy storage_key các bản cũ qua DB của fixture (SQLite in-memory).
        # doc["id"] là str (từ JSON) — cột Uuid cần UUID object.
        with db_session_factory() as db:
            keys = set(
                db.scalars(
                    select(DocumentVersion.storage_key).where(
                        DocumentVersion.document_id == uuid.UUID(doc["id"])
                    )
                )
            )
        assert keys, "phải có ít nhất 1 bản cũ trước khi xóa tài liệu"

        resp = client.delete(
            f"/api/v1/documents/{doc['id']}", headers=auth_headers
        )
        assert resp.status_code == 200
        for key in keys:
            assert not storage_service.document_path(key).exists()


class TestVersionQuota:
    def test_quota_counts_old_versions(self, client, auth_headers, monkeypatch):
        """Quota phải tính cả bytes các bản cũ (không cho lách hạn mức).

        Quota 1 MB, 3 bước (đều < quota nếu chỉ tính bản hiện tại):
        - v1 = 300 KB → OK (300 KB dùng).
        - v2 = 500 KB → OK (tại thời điểm check chưa có bản cũ nào).
        - v3 = 300 KB → PHẢI BỊ CHẶN: 500 (hiện tại) + 300 (bản cũ) + 300 (mới)
          > 1 MB. Nếu quota không tính bản cũ thì 500 + 300 = 800 KB → lọt.
        """
        from app.core.config import get_settings

        monkeypatch.setenv("USER_STORAGE_QUOTA_MB", "1")
        get_settings.cache_clear()
        try:
            doc = _upload_txt(client, auth_headers, "a.txt", "v" * 300_000).json()
            ok = client.post(
                f"/api/v1/documents/{doc['id']}/versions",
                headers=auth_headers,
                files={"file": ("a.txt", make_txt("w" * 500_000), "text/plain")},
            )
            assert ok.status_code == 201

            blocked = client.post(
                f"/api/v1/documents/{doc['id']}/versions",
                headers=auth_headers,
                files={"file": ("a.txt", make_txt("x" * 300_000), "text/plain")},
            )
            assert blocked.status_code == 413
        finally:
            monkeypatch.delenv("USER_STORAGE_QUOTA_MB", raising=False)
            get_settings.cache_clear()


class TestDiffService:
    def test_compute_line_diff_finds_changes(self):
        diff = diff_service.compute_line_diff("a\nb\nc", "a\nx\nc")
        joined = "\n".join(diff)
        assert "-b" in joined
        assert "+x" in joined

    def test_diff_stats_counts(self):
        diff = diff_service.compute_line_diff("a\nb", "a\nx\ny")
        stats = diff_service.diff_stats(diff)
        assert stats["added"] == 2
        assert stats["removed"] == 1

    def test_identical_text_no_diff(self):
        assert diff_service.compute_line_diff("same", "same") == []

    def test_summarize_changes_calls_ai(self):
        with patch.object(diff_service.ai_service, "request_anthropic") as mock:
            mock.return_value = "- Điều 4 đổi số tiền"
            result = diff_service.summarize_changes("a", "b")
        assert result == "- Điều 4 đổi số tiền"
        mock.assert_called_once()

    def test_summarize_identical_skips_ai(self):
        with patch.object(diff_service.ai_service, "request_anthropic") as mock:
            result = diff_service.summarize_changes("same", "same")
        assert "không có khác biệt" in result
        mock.assert_not_called()


class TestDiffEndpoint:
    def test_diff_with_current(self, client, auth_headers, monkeypatch):
        doc = _upload_txt(client, auth_headers, "a.txt", "dong mot\ndong hai").json()
        client.post(
            f"/api/v1/documents/{doc['id']}/versions",
            headers=auth_headers,
            files={
                "file": (
                    "a.txt",
                    make_txt("dong mot\ndong ba"),
                    "text/plain",
                )
            },
        )
        versions = client.get(
            f"/api/v1/documents/{doc['id']}/versions", headers=auth_headers
        ).json()

        # monkeypatch credit + AI để test luồng API không tốn tiền thật
        from app.services import credit_service

        monkeypatch.setattr(credit_service, "charge", lambda db, user: None)
        with patch.object(
            diff_service.ai_service, "request_anthropic", return_value="tóm tắt giả"
        ):
            resp = client.post(
                f"/api/v1/documents/{doc['id']}/versions/diff",
                headers=auth_headers,
                json={"old_version_id": versions[0]["id"], "new_version_id": None},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["added"] == 1
        assert body["removed"] == 1
        assert body["ai_summary"] == "tóm tắt giả"

    def test_diff_identical_no_credit(self, client, auth_headers, monkeypatch):
        doc = _upload_txt(client, auth_headers, "a.txt", "giống nhau").json()
        client.post(
            f"/api/v1/documents/{doc['id']}/versions",
            headers=auth_headers,
            files={"file": ("a.txt", make_txt("giống nhau"), "text/plain")},
        )
        versions = client.get(
            f"/api/v1/documents/{doc['id']}/versions", headers=auth_headers
        ).json()

        from app.services import credit_service

        called = {"n": 0}

        def _fail(db, user):
            called["n"] += 1
            raise AssertionError("không được trừ credit khi 2 bản giống nhau")

        monkeypatch.setattr(credit_service, "charge", _fail)
        resp = client.post(
            f"/api/v1/documents/{doc['id']}/versions/diff",
            headers=auth_headers,
            json={"old_version_id": versions[0]["id"]},
        )
        assert resp.status_code == 200
        assert resp.json()["diff"] == []
        assert called["n"] == 0
