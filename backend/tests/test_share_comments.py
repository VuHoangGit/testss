"""Test P2: bình luận ghim vị trí trên share link (SRS §8).

Bắt buộc: link view → 403; link comment → 201; owner xóa được, guest không;
quá 500 → 400; reply đúng 1 cấp.
"""

import pytest

from app.models.document_share import DocumentShare
from app.models.share_comment import ShareComment
from app.services.share_service import hash_token


def make_pdf() -> bytes:
    import io

    from pypdf import PdfWriter

    writer = PdfWriter()
    for _ in range(5):
        writer.add_blank_page(width=200, height=200)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


@pytest.fixture()
def auth_headers(make_token):
    token = make_token(sub="sub-owner", email="owner@gmail.com", name="Owner")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def other_headers(make_token):
    token = make_token(sub="sub-other", email="other@gmail.com", name="Other")
    return {"Authorization": f"Bearer {token}"}


def _upload(client, headers) -> dict:
    resp = client.post(
        "/api/v1/documents",
        headers=headers,
        files={"file": ("tailieu.pdf", make_pdf(), "application/pdf")},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _create_share(client, headers, doc_id: str, permission: str = "view") -> str:
    resp = client.post(
        f"/api/v1/documents/{doc_id}/shares",
        headers=headers,
        json={"permission": permission},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["share_url"].split("share=")[-1]


def _comment_payload(**override) -> dict:
    payload = {
        "page_number": 3,
        "norm_x": 0.4,
        "norm_y": 0.6,
        "author_name": "Khách A",
        "body": "Điều khoản 4 cần xem lại",
    }
    payload.update(override)
    return payload


class TestPublicCommentApi:
    def test_view_link_cannot_comment_403(self, client, auth_headers):
        doc = _upload(client, auth_headers)
        token = _create_share(client, auth_headers, doc["id"], permission="view")
        resp = client.post(
            f"/api/v1/public/shares/{token}/comments", json=_comment_payload()
        )
        assert resp.status_code == 403
        assert resp.json()["detail"] == "Link này chỉ cho phép xem"

    def test_comment_link_create_and_list(self, client, auth_headers):
        doc = _upload(client, auth_headers)
        token = _create_share(client, auth_headers, doc["id"], permission="comment")
        resp = client.post(
            f"/api/v1/public/shares/{token}/comments", json=_comment_payload()
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["author_name"] == "Khách A"
        assert body["page_number"] == 3
        assert "share_id" not in body

        listing = client.get(f"/api/v1/public/shares/{token}/comments").json()
        assert len(listing) == 1
        # sort (page_number, created_at)
        assert listing[0]["norm_x"] == pytest.approx(0.4)

    def test_empty_author_defaults_to_khach(self, client, auth_headers):
        doc = _upload(client, auth_headers)
        token = _create_share(client, auth_headers, doc["id"], permission="comment")
        resp = client.post(
            f"/api/v1/public/shares/{token}/comments",
            json=_comment_payload(author_name="   "),
        )
        assert resp.status_code == 201
        assert resp.json()["author_name"] == "Khách"

    def test_body_validation_1_to_2000(self, client, auth_headers):
        doc = _upload(client, auth_headers)
        token = _create_share(client, auth_headers, doc["id"], permission="comment")
        empty = client.post(
            f"/api/v1/public/shares/{token}/comments", json=_comment_payload(body="")
        )
        too_long = client.post(
            f"/api/v1/public/shares/{token}/comments",
            json=_comment_payload(body="x" * 2001),
        )
        assert empty.status_code == 422
        assert too_long.status_code == 422

    def test_norm_out_of_range_422(self, client, auth_headers):
        doc = _upload(client, auth_headers)
        token = _create_share(client, auth_headers, doc["id"], permission="comment")
        resp = client.post(
            f"/api/v1/public/shares/{token}/comments",
            json=_comment_payload(norm_x=1.5, norm_y=-0.1),
        )
        assert resp.status_code == 422

    def test_reply_one_level_only(self, client, auth_headers):
        doc = _upload(client, auth_headers)
        token = _create_share(client, auth_headers, doc["id"], permission="comment")
        root = client.post(
            f"/api/v1/public/shares/{token}/comments", json=_comment_payload()
        ).json()
        # Reply cấp 1 OK
        reply = client.post(
            f"/api/v1/public/shares/{token}/comments",
            json=_comment_payload(parent_id=root["id"], body="Đồng ý"),
        )
        assert reply.status_code == 201
        # Reply cấp 2 (trả lời reply) → 400
        nested = client.post(
            f"/api/v1/public/shares/{token}/comments",
            json=_comment_payload(parent_id=reply.json()["id"], body="sâu hơn"),
        )
        assert nested.status_code == 400
        # Reply vào comment của link khác → 400
        other_doc = _upload(client, auth_headers)
        other_token = _create_share(client, auth_headers, other_doc["id"], permission="comment")
        cross = client.post(
            f"/api/v1/public/shares/{other_token}/comments",
            json=_comment_payload(parent_id=root["id"], body="lạ"),
        )
        assert cross.status_code == 400

    def test_max_500_comments(self, client, auth_headers, db_session_factory):
        doc = _upload(client, auth_headers)
        token = _create_share(client, auth_headers, doc["id"], permission="comment")
        # Nhét thẳng DB cho nhanh (POST 500 lần sẽ chậm + rate limit)
        with db_session_factory() as db:
            share = db.query(DocumentShare).one()
            for i in range(500):
                db.add(
                    ShareComment(
                        share_id=share.id,
                        page_number=1,
                        norm_x=0.5,
                        norm_y=0.5,
                        author_name="Khách",
                        body=f"c {i}",
                    )
                )
            db.commit()
        resp = client.post(
            f"/api/v1/public/shares/{token}/comments", json=_comment_payload()
        )
        assert resp.status_code == 400
        assert resp.json()["detail"] == "Chủ đề đã đầy"

    def test_comments_of_dead_link_404(self, client, auth_headers):
        doc = _upload(client, auth_headers)
        token = _create_share(client, auth_headers, doc["id"], permission="comment")
        client.delete(f"/api/v1/documents/{doc['id']}", headers=auth_headers)
        resp = client.get(f"/api/v1/public/shares/{token}/comments")
        assert resp.status_code == 404


class TestOwnerCommentApi:
    def test_owner_lists_all_comments_across_shares(self, client, auth_headers):
        doc = _upload(client, auth_headers)
        token1 = _create_share(client, auth_headers, doc["id"], permission="comment")
        token2 = _create_share(client, auth_headers, doc["id"], permission="comment")
        client.post(
            f"/api/v1/public/shares/{token1}/comments", json=_comment_payload(body="A1")
        )
        client.post(
            f"/api/v1/public/shares/{token2}/comments",
            json=_comment_payload(page_number=2, body="B1"),
        )
        listing = client.get(
            f"/api/v1/documents/{doc['id']}/share-comments", headers=auth_headers
        ).json()
        assert {c["body"] for c in listing} == {"A1", "B1"}
        # Owner view kèm share_id
        assert all("share_id" in c for c in listing)

    def test_owner_delete_comment(self, client, auth_headers):
        doc = _upload(client, auth_headers)
        token = _create_share(client, auth_headers, doc["id"], permission="comment")
        created = client.post(
            f"/api/v1/public/shares/{token}/comments", json=_comment_payload()
        ).json()
        resp = client.delete(
            f"/api/v1/documents/{doc['id']}/share-comments/{created['id']}",
            headers=auth_headers,
        )
        assert resp.status_code == 204
        assert client.get(f"/api/v1/public/shares/{token}/comments").json() == []

    def test_delete_reply_cascades_children(self, client, auth_headers):
        doc = _upload(client, auth_headers)
        token = _create_share(client, auth_headers, doc["id"], permission="comment")
        root = client.post(
            f"/api/v1/public/shares/{token}/comments", json=_comment_payload()
        ).json()
        client.post(
            f"/api/v1/public/shares/{token}/comments",
            json=_comment_payload(parent_id=root["id"], body="reply"),
        ).json()
        client.delete(
            f"/api/v1/documents/{doc['id']}/share-comments/{root['id']}",
            headers=auth_headers,
        )
        listing = client.get(f"/api/v1/public/shares/{token}/comments").json()
        assert listing == []  # reply con đi theo (cascade)

    def test_other_user_cannot_touch_comments(self, client, auth_headers, other_headers):
        doc = _upload(client, auth_headers)
        token = _create_share(client, auth_headers, doc["id"], permission="comment")
        created = client.post(
            f"/api/v1/public/shares/{token}/comments", json=_comment_payload()
        ).json()
        # Người khác: không list, không xóa
        assert (
            client.get(
                f"/api/v1/documents/{doc['id']}/share-comments", headers=other_headers
            ).status_code
            == 404
        )
        assert (
            client.delete(
                f"/api/v1/documents/{doc['id']}/share-comments/{created['id']}",
                headers=other_headers,
            ).status_code
            == 404
        )
        # Guest không có endpoint xóa — route public DELETE không tồn tại
        assert (
            client.delete(
                f"/api/v1/public/shares/{token}/comments/{created['id']}"
            ).status_code
            == 404
        )

    def test_comment_of_another_document_404(self, client, auth_headers):
        doc1 = _upload(client, auth_headers)
        doc2 = _upload(client, auth_headers)
        token1 = _create_share(client, auth_headers, doc1["id"], permission="comment")
        created = client.post(
            f"/api/v1/public/shares/{token1}/comments", json=_comment_payload()
        ).json()
        resp = client.delete(
            f"/api/v1/documents/{doc2['id']}/share-comments/{created['id']}",
            headers=auth_headers,
        )
        assert resp.status_code == 404


class TestTokenHashing:
    def test_db_stores_hash_not_raw_token(self, client, auth_headers, db_session_factory):
        doc = _upload(client, auth_headers)
        token = _create_share(client, auth_headers, doc["id"])
        with db_session_factory() as db:
            row = db.query(DocumentShare).one()
            assert row.token_hash == hash_token(token)
            assert len(row.token_hash) == 64
            assert token not in row.token_hash  # không lưu raw
