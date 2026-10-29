"""Test Favorites + Recent + search: cột mới documents.is_favorite/last_opened_at."""

import io
import time

import pytest
from pypdf import PdfWriter


def make_pdf(pages: int = 1) -> bytes:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=200, height=200)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


@pytest.fixture()
def auth_headers(make_token):
    token = make_token(sub="sub-fav", email="fav@gmail.com", name="Fav")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def other_headers(make_token):
    token = make_token(sub="sub-fav-other", email="favother@gmail.com", name="Other")
    return {"Authorization": f"Bearer {token}"}


def _upload(client, headers, name: str):
    return client.post(
        "/api/v1/documents",
        headers=headers,
        files={"file": (name, make_pdf(), "application/pdf")},
    )


class TestFavorite:
    def test_toggle_favorite_and_filter(self, client, auth_headers):
        a = _upload(client, auth_headers, "hop-dong.pdf").json()
        b = _upload(client, auth_headers, "hoa-don.pdf").json()

        # Gắn sao a, gỡ sao (idempotent qua body), b không đụng tới
        resp = client.patch(
            f"/api/v1/documents/{a['id']}/favorite",
            headers=auth_headers,
            json={"favorite": True},
        )
        assert resp.status_code == 200
        assert resp.json()["is_favorite"] is True

        favs = client.get(
            "/api/v1/documents", headers=auth_headers, params={"favorites_only": True}
        ).json()
        assert [d["original_name"] for d in favs] == ["hop-dong.pdf"]

        client.patch(
            f"/api/v1/documents/{a['id']}/favorite",
            headers=auth_headers,
            json={"favorite": False},
        )
        assert (
            client.get(
                "/api/v1/documents",
                headers=auth_headers,
                params={"favorites_only": True},
            ).json()
            == []
        )
        assert b["is_favorite"] is False  # mặc định chưa gắn sao

    def test_favorite_of_other_user_404(self, client, auth_headers, other_headers):
        doc = _upload(client, auth_headers, "bi-mat.pdf").json()
        resp = client.patch(
            f"/api/v1/documents/{doc['id']}/favorite",
            headers=other_headers,
            json={"favorite": True},
        )
        assert resp.status_code == 404


class TestRecent:
    def test_open_updates_last_opened_and_sorts(self, client, auth_headers):
        a = _upload(client, auth_headers, "cu.pdf").json()   # tải lên trước
        b = _upload(client, auth_headers, "moi.pdf").json()
        assert a["last_opened_at"] is None

        # Mở a, chờ 1 tick rồi mở b → b phải đứng trước a khi sort=recent
        assert (
            client.post(f"/api/v1/documents/{a['id']}/open", headers=auth_headers).status_code
            == 200
        )
        time.sleep(0.01)
        client.post(f"/api/v1/documents/{b['id']}/open", headers=auth_headers)

        recent = client.get(
            "/api/v1/documents", headers=auth_headers, params={"sort": "recent"}
        ).json()
        assert [d["original_name"] for d in recent] == ["moi.pdf", "cu.pdf"]
        assert recent[1]["last_opened_at"] is not None

        # sort mặc định không phải recent (đủ 2 file, không văng lỗi)
        default = client.get("/api/v1/documents", headers=auth_headers).json()
        assert {d["original_name"] for d in default} == {"moi.pdf", "cu.pdf"}

    def test_unopened_documents_sort_last(self, client, auth_headers):
        _upload(client, auth_headers, "chua-mo.pdf")
        opened = _upload(client, auth_headers, "da-mo.pdf").json()
        client.post(f"/api/v1/documents/{opened['id']}/open", headers=auth_headers)

        recent = client.get(
            "/api/v1/documents", headers=auth_headers, params={"sort": "recent"}
        ).json()
        assert recent[0]["original_name"] == "da-mo.pdf"
        assert recent[-1]["original_name"] == "chua-mo.pdf"

    def test_open_of_other_user_404(self, client, auth_headers, other_headers):
        doc = _upload(client, auth_headers, "rieng.pdf").json()
        assert (
            client.post(
                f"/api/v1/documents/{doc['id']}/open", headers=other_headers
            ).status_code
            == 404
        )


class TestSearch:
    def test_search_by_name_case_insensitive(self, client, auth_headers):
        _upload(client, auth_headers, "Hop-Dong-2026.pdf")
        _upload(client, auth_headers, "hoa-don.pdf")

        hits = client.get(
            "/api/v1/documents", headers=auth_headers, params={"search": "hop-dong"}
        ).json()
        assert [d["original_name"] for d in hits] == ["Hop-Dong-2026.pdf"]

        # Tìm gần đúng một phần, không phân biệt hoa thường
        hits = client.get(
            "/api/v1/documents", headers=auth_headers, params={"search": "HOA"}
        ).json()
        assert [d["original_name"] for d in hits] == ["hoa-don.pdf"]

    def test_search_scoped_to_owner(self, client, auth_headers, other_headers):
        _upload(client, auth_headers, "cua-toi.pdf")
        assert (
            client.get(
                "/api/v1/documents", headers=other_headers, params={"search": "cua-toi"}
            ).json()
            == []
        )

    def test_search_no_match_returns_empty(self, client, auth_headers):
        _upload(client, auth_headers, "khong-lien-quan.pdf")
        assert (
            client.get(
                "/api/v1/documents", headers=auth_headers, params={"search": "zzz"}
            ).json()
            == []
        )
