"""Test P1: link chia sẻ chỉ xem (SRS §8).

Bắt buộc: metadata không lộ id nội bộ; inline/attachment theo MIME; 404 chung
chung cho mọi link chết; owner-check trả 404; cascade khi xóa tài liệu; rate
limit IP; giới hạn 10 link active.
"""

import io
import uuid as uuid_mod

import pytest
from pypdf import PdfReader, PdfWriter

from app.core.config import get_settings
from app.core.ratelimit import reset_rate_limits
from app.models.document_share import DocumentShare


def make_pdf(pages: int = 1) -> bytes:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=200, height=200)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


@pytest.fixture()
def auth_headers(make_token):
    token = make_token(sub="sub-owner", email="owner@gmail.com", name="Chủ Tài Sản")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def other_headers(make_token):
    token = make_token(sub="sub-other", email="other@gmail.com", name="Người Khác")
    return {"Authorization": f"Bearer {token}"}


def _upload(client, headers, name: str, data: bytes) -> dict:
    resp = client.post(
        "/api/v1/documents", headers=headers, files={"file": (name, data, "application/pdf")}
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _create_share(client, headers, doc_id: str, **payload) -> dict:
    resp = client.post(f"/api/v1/documents/{doc_id}/shares", headers=headers, json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


class TestCreateAndList:
    def test_create_returns_share_url_once(self, client, auth_headers):
        doc = _upload(client, auth_headers, "hop-dong.pdf", make_pdf(2))
        share = _create_share(
            client, auth_headers, doc["id"], permission="view", expires_in_hours=24
        )
        # Metadata cơ bản
        assert share["permission"] == "view"
        assert share["is_active"] is True
        assert share["view_count"] == 0
        assert share["expires_at"] is not None
        # URL có dạng {base}/?share={token}, token đủ dài
        assert share["share_url"].startswith(get_settings().public_web_base_url)
        token = share["share_url"].split("share=")[-1]
        assert len(token) >= 24
        # KHÔNG có document_id / token_hash trong response
        assert "document_id" not in share
        assert "token_hash" not in share

    def test_list_shows_all_including_revoked_without_token(self, client, auth_headers):
        doc = _upload(client, auth_headers, "a.pdf", make_pdf())
        first = _create_share(client, auth_headers, doc["id"])
        second = _create_share(client, auth_headers, doc["id"])
        # thu hồi link đầu
        resp = client.delete(
            f"/api/v1/documents/{doc['id']}/shares/{first['id']}", headers=auth_headers
        )
        assert resp.status_code == 204

        listing = client.get(
            f"/api/v1/documents/{doc['id']}/shares", headers=auth_headers
        ).json()
        assert len(listing) == 2
        by_id = {s["id"]: s for s in listing}
        assert by_id[first["id"]]["is_active"] is False
        assert by_id[second["id"]]["is_active"] is True
        # danh sách KHÔNG trả lại URL (token không lưu được)
        assert all(s["share_url"] == "" for s in listing)

    def test_owner_check_returns_404_for_stranger(self, client, auth_headers, other_headers):
        doc = _upload(client, auth_headers, "rieng.pdf", make_pdf())
        # Người khác tạo/list/thu hồi → 404 (không 403 — tránh lộ sự tồn tại)
        resp = client.post(
            f"/api/v1/documents/{doc['id']}/shares",
            headers=other_headers,
            json={"permission": "view"},
        )
        assert resp.status_code == 404
        resp = client.get(
            f"/api/v1/documents/{doc['id']}/shares", headers=other_headers
        )
        assert resp.status_code == 404
        resp = client.delete(
            f"/api/v1/documents/{doc['id']}/shares/{uuid_mod.uuid4()}",
            headers=other_headers,
        )
        assert resp.status_code == 404

    def test_revoke_unknown_share_404(self, client, auth_headers):
        doc = _upload(client, auth_headers, "a.pdf", make_pdf())
        resp = client.delete(
            f"/api/v1/documents/{doc['id']}/shares/{uuid_mod.uuid4()}",
            headers=auth_headers,
        )
        assert resp.status_code == 404

    def test_max_10_active_links(self, client, auth_headers):
        doc = _upload(client, auth_headers, "a.pdf", make_pdf())
        for _ in range(10):
            _create_share(client, auth_headers, doc["id"])
        resp = client.post(
            f"/api/v1/documents/{doc['id']}/shares",
            headers=auth_headers,
            json={"permission": "view"},
        )
        assert resp.status_code == 400
        assert "10" in resp.json()["detail"]
        # Thu hồi 1 link → tạo lại được
        listing = client.get(
            f"/api/v1/documents/{doc['id']}/shares", headers=auth_headers
        ).json()
        client.delete(
            f"/api/v1/documents/{doc['id']}/shares/{listing[0]['id']}",
            headers=auth_headers,
        )
        assert (
            client.post(
                f"/api/v1/documents/{doc['id']}/shares",
                headers=auth_headers,
                json={"permission": "view"},
            ).status_code
            == 201
        )

    def test_invalid_expiry_rejected(self, client, auth_headers):
        doc = _upload(client, auth_headers, "a.pdf", make_pdf())
        resp = client.post(
            f"/api/v1/documents/{doc['id']}/shares",
            headers=auth_headers,
            json={"permission": "view", "expires_in_hours": 3},
        )
        assert resp.status_code == 400

    def test_invalid_permission_rejected(self, client, auth_headers):
        doc = _upload(client, auth_headers, "a.pdf", make_pdf())
        resp = client.post(
            f"/api/v1/documents/{doc['id']}/shares",
            headers=auth_headers,
            json={"permission": "edit"},
        )
        assert resp.status_code == 422  # pydantic pattern chặn ở tầng schema


class TestPublicAccess:
    def test_metadata_has_no_internal_ids(self, client, auth_headers):
        doc = _upload(client, auth_headers, "bao-cao.pdf", make_pdf(3))
        share = _create_share(client, auth_headers, doc["id"])
        token = share["share_url"].split("share=")[-1]

        meta = client.get(f"/api/v1/public/shares/{token}").json()
        assert meta["file_name"] == "bao-cao.pdf"
        assert meta["mime_type"] == "application/pdf"
        assert meta["page_count"] == 3
        assert meta["permission"] == "view"
        assert meta["owner_name"] == "Chủ Tài Sản"
        # KHÔNG trả bất kỳ id nội bộ nào (FR-2.1)
        assert set(meta.keys()) == {
            "file_name",
            "mime_type",
            "size_bytes",
            "page_count",
            "permission",
            "expires_at",
            "owner_name",
        }

    def test_file_inline_for_pdf(self, client, auth_headers):
        data = make_pdf(2)
        doc = _upload(client, auth_headers, "hop-dong.pdf", data)
        share = _create_share(client, auth_headers, doc["id"])
        token = share["share_url"].split("share=")[-1]

        resp = client.get(f"/api/v1/public/shares/{token}/file")
        assert resp.status_code == 200
        assert resp.content == data
        disposition = resp.headers["content-disposition"]
        assert disposition.startswith("inline")
        assert "hop-dong.pdf" in disposition
        assert resp.headers["x-content-type-options"] == "nosniff"

    def test_file_attachment_for_image(self, client, auth_headers):
        resp0 = client.post(
            "/api/v1/documents",
            headers=auth_headers,
            files={"file": ("anh.png", PNG_BYTES, "image/png")},
        )
        assert resp0.status_code == 201, resp0.text
        doc = resp0.json()
        share = _create_share(client, auth_headers, doc["id"])
        token = share["share_url"].split("share=")[-1]

        resp = client.get(f"/api/v1/public/shares/{token}/file")
        assert resp.status_code == 200
        assert resp.headers["content-disposition"].startswith("attachment")

    def test_view_count_increments(self, client, auth_headers):
        doc = _upload(client, auth_headers, "a.pdf", make_pdf())
        share = _create_share(client, auth_headers, doc["id"])
        token = share["share_url"].split("share=")[-1]

        client.get(f"/api/v1/public/shares/{token}/file")
        client.get(f"/api/v1/public/shares/{token}/file")
        listing = client.get(
            f"/api/v1/documents/{doc['id']}/shares", headers=auth_headers
        ).json()
        assert sum(s["view_count"] for s in listing) == 2

    def test_wrong_token_404_generic(self, client, auth_headers):
        doc = _upload(client, auth_headers, "a.pdf", make_pdf())
        _create_share(client, auth_headers, doc["id"])
        for token in ("sai-token-hehe", "x" * 32, ""):
            resp = client.get(f"/api/v1/public/shares/{token}")
            if token == "":
                continue  # route khớp rỗng là 404 của router, bỏ qua
            assert resp.status_code == 404
            assert resp.json()["detail"] == "Link không tồn tại hoặc đã hết hạn"

    def test_revoked_link_404_same_message(self, client, auth_headers):
        doc = _upload(client, auth_headers, "a.pdf", make_pdf())
        share = _create_share(client, auth_headers, doc["id"])
        token = share["share_url"].split("share=")[-1]
        client.delete(
            f"/api/v1/documents/{doc['id']}/shares/{share['id']}", headers=auth_headers
        )
        for path in ("", "/file", "/comments"):
            resp = client.get(f"/api/v1/public/shares/{token}{path}")
            assert resp.status_code == 404
            assert resp.json()["detail"] == "Link không tồn tại hoặc đã hết hạn"

    def test_expired_link_404(self, client, auth_headers, db_session_factory):
        from datetime import UTC, datetime, timedelta

        doc = _upload(client, auth_headers, "a.pdf", make_pdf())
        share = _create_share(client, auth_headers, doc["id"], expires_in_hours=24)
        token = share["share_url"].split("share=")[-1]
        # Ép hết hạn trong quá khứ trực tiếp qua DB (không đợi thật)
        with db_session_factory() as db:
            row = db.query(DocumentShare).filter_by(id=uuid_mod.UUID(share["id"])).one()
            row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
            db.commit()

        resp = client.get(f"/api/v1/public/shares/{token}")
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Link không tồn tại hoặc đã hết hạn"

    def test_delete_document_kills_link(self, client, auth_headers, db_session_factory):
        doc = _upload(client, auth_headers, "a.pdf", make_pdf())
        share = _create_share(client, auth_headers, doc["id"])
        token = share["share_url"].split("share=")[-1]

        client.delete(f"/api/v1/documents/{doc['id']}", headers=auth_headers)
        resp = client.get(f"/api/v1/public/shares/{token}")
        assert resp.status_code == 404
        # DB cascade: không còn share nào của tài liệu
        with db_session_factory() as db:
            assert db.query(DocumentShare).count() == 0

    def test_share_serves_current_version_after_restore(self, client, auth_headers):
        """FR-1.8: link luôn phục vụ bản hiện tại."""
        doc = _upload(client, auth_headers, "goc.pdf", make_pdf(1))
        share = _create_share(client, auth_headers, doc["id"])
        token = share["share_url"].split("share=")[-1]
        # Upload bản mới (2 trang)
        resp = client.post(
            f"/api/v1/documents/{doc['id']}/versions",
            headers=auth_headers,
            files={"file": ("moi.pdf", make_pdf(2), "application/pdf")},
            data={"label": "bản mới"},
        )
        assert resp.status_code == 201, resp.text
        file_resp = client.get(f"/api/v1/public/shares/{token}/file")
        assert len(PdfReader(io.BytesIO(file_resp.content)).pages) == 2


class TestRateLimit:
    """Rate limit theo IP — bật qua env như test_security (settings cache_clear)."""

    @staticmethod
    def _env_ctx():
        import os
        from collections.abc import Iterator
        from contextlib import contextmanager

        @contextmanager
        def _ctx(values: dict[str, str]) -> Iterator[None]:
            previous = {key: os.environ.get(key) for key in values}
            try:
                os.environ.update(values)
                get_settings.cache_clear()
                yield
            finally:
                for key, old in previous.items():
                    if old is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = old
                get_settings.cache_clear()

        return _ctx

    def test_meta_rate_limit_429(self, client, auth_headers):
        reset_rate_limits()
        doc = _upload(client, auth_headers, "a.pdf", make_pdf())
        share = _create_share(client, auth_headers, doc["id"])
        token = share["share_url"].split("share=")[-1]
        try:
            with self._env_ctx()({
                "RATE_LIMIT_ENABLED": "true",
                "RATE_LIMIT_SHARE_META_PER_MINUTE": "3",
            }):
                codes = [
                    client.get(
                        f"/api/v1/public/shares/{token}",
                        headers={"X-Forwarded-For": "203.0.113.9"},
                    ).status_code
                    for _ in range(4)
                ]
            assert codes[:3] == [200, 200, 200]
            assert codes[3] == 429
        finally:
            reset_rate_limits()

    def test_rate_limit_is_per_ip(self, client, auth_headers):
        reset_rate_limits()
        doc = _upload(client, auth_headers, "a.pdf", make_pdf())
        share = _create_share(client, auth_headers, doc["id"])
        token = share["share_url"].split("share=")[-1]
        try:
            with self._env_ctx()({
                "RATE_LIMIT_ENABLED": "true",
                "RATE_LIMIT_SHARE_META_PER_MINUTE": "1",
            }):
                first = client.get(
                    f"/api/v1/public/shares/{token}",
                    headers={"X-Forwarded-For": "203.0.113.1"},
                )
                blocked = client.get(
                    f"/api/v1/public/shares/{token}",
                    headers={"X-Forwarded-For": "203.0.113.1"},
                )
                other_ip = client.get(
                    f"/api/v1/public/shares/{token}",
                    headers={"X-Forwarded-For": "203.0.113.2"},
                )
            assert (first.status_code, blocked.status_code, other_ip.status_code) == (
                200,
                429,  # IP đầu bị chặn
                200,  # IP khác vẫn được
            )
        finally:
            reset_rate_limits()
