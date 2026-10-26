"""Test xác thực Supabase Auth: verify JWT + resolve user local.

JWT ký thật bằng RSA của test (conftest), verify đi qua đúng code production.
"""

from datetime import datetime

import pytest

from app.core import security
from app.core.config import get_settings
from app.core.security import AuthError
from app.models.user import User
from app.services import auth_service


class TestVerifySupabaseToken:
    def test_valid_token_returns_payload(self, make_token):
        payload = security.verify_supabase_token(make_token(sub="sub-abc", email="a@gmail.com"))
        assert payload["sub"] == "sub-abc"
        assert payload["email_verified"] is True

    def test_rejects_wrong_issuer(self, make_token):
        token = make_token(issuer="https://khac.supabase.co/auth/v1")
        with pytest.raises(AuthError):
            security.verify_supabase_token(token)

    def test_rejects_wrong_audience(self, make_token):
        with pytest.raises(AuthError):
            security.verify_supabase_token(make_token(audience="anon"))

    def test_rejects_expired_token(self, make_token):
        with pytest.raises(AuthError):
            security.verify_supabase_token(make_token(expires_in_seconds=-10))


class TestResolveSupabaseUser:
    def test_new_email_creates_user_normalized(self, db_session_factory):
        with db_session_factory() as db:
            user = auth_service.resolve_supabase_user(
                db, "sub-new", email="New@Gmail.COM", name="Người mới", avatar_url="http://pic"
            )
            db.commit()
            assert user.supabase_id == "sub-new"
            assert user.email == "new@gmail.com"
            assert user.name == "Người mới"
            assert user.avatar_url == "http://pic"

    def test_same_sub_returns_same_user(self, db_session_factory):
        with db_session_factory() as db:
            first = auth_service.resolve_supabase_user(
                db, "sub-x", email="x@gmail.com", name=None, avatar_url=None
            )
            db.commit()
            again = auth_service.resolve_supabase_user(
                db, "sub-x", email="x@gmail.com", name=None, avatar_url=None
            )
            assert again.id == first.id
            assert db.query(User).count() == 1

    def test_legacy_user_matched_by_email_keeps_id_and_documents(
        self, db_session_factory
    ):
        """User tạo trước thời Supabase: đăng nhập lần đầu gắn supabase_id,
        giữ nguyên id (→ documents/folders cũ vẫn thuộc user này)."""
        with db_session_factory() as db:
            legacy = User(email="legacy@gmail.com", name="Tên cũ")
            db.add(legacy)
            db.commit()
            legacy_id = legacy.id

            got = auth_service.resolve_supabase_user(
                db, "sub-legacy", email="legacy@gmail.com", name="Tên mới", avatar_url=None
            )
            db.commit()
            assert got.id == legacy_id
            assert got.supabase_id == "sub-legacy"
            assert got.name == "Tên cũ"  # không đè dữ liệu đã có
            assert db.query(User).count() == 1

    def test_duplicate_email_picks_newest_row(self, db_session_factory):
        with db_session_factory() as db:
            old = User(email="dup@gmail.com", created_at=datetime(2020, 1, 1))
            new = User(email="dup@gmail.com", created_at=datetime(2021, 6, 1))
            db.add_all([old, new])
            db.commit()

            got = auth_service.resolve_supabase_user(
                db, "sub-dup", email="dup@gmail.com", name=None, avatar_url=None
            )
            db.commit()
            assert got.id == new.id
            assert got.supabase_id == "sub-dup"

    def test_unknown_sub_without_email_rejected(self, db_session_factory):
        with db_session_factory() as db:
            with pytest.raises(AuthError):
                auth_service.resolve_supabase_user(
                    db, "sub-no-email", email=None, name=None, avatar_url=None
                )

    def test_known_sub_passes_even_if_email_unverified(self, db_session_factory):
        """Đã từng đăng nhập (sub đã gắn) thì token gia hạn sau không bị chặn."""
        with db_session_factory() as db:
            first = auth_service.resolve_supabase_user(
                db, "sub-known", email="k@gmail.com", name=None, avatar_url=None
            )
            db.commit()
            again = auth_service.resolve_supabase_user(
                db, "sub-known", email=None, name=None, avatar_url=None
            )
            assert again.id == first.id


class TestAuthMeEndpoint:
    def test_returns_profile_created_from_token(self, client, make_token):
        token = make_token(sub="sub-me", email="me@gmail.com", name="Tôi")
        resp = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["email"] == "me@gmail.com"
        assert body["name"] == "Tôi"

    def test_requires_bearer_token(self, client):
        assert client.get("/api/v1/auth/me").status_code == 401

    def test_rejects_unverified_email_for_new_user(self, client, make_token):
        token = make_token(sub="sub-unverified", email="u@gmail.com", email_verified=False)
        resp = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 401
        assert "xác thực email" in resp.json()["detail"]

    def test_rejects_disallowed_email_domain(self, client, make_token, monkeypatch):
        monkeypatch.setattr(get_settings(), "allowed_email_domains", "congty.vn")
        token = make_token(sub="sub-dom", email="someone@gmail.com")
        assert (
            client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code
            == 401
        )

    def test_allows_configured_email_domain(self, client, make_token, monkeypatch):
        monkeypatch.setattr(get_settings(), "allowed_email_domains", "congty.vn")
        token = make_token(sub="sub-ok", email="ai@congty.vn")
        assert (
            client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code
            == 200
        )

    def test_google_metadata_maps_to_name_and_avatar(
        self, client, make_token, db_session_factory
    ):
        token = make_token(
            sub="sub-gg", email="gg@gmail.com", name="Google User", avatar_url="http://pic"
        )
        resp = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200, resp.text
        with db_session_factory() as db:
            user = db.query(User).one()
            assert user.name == "Google User"
            assert user.avatar_url == "http://pic"
