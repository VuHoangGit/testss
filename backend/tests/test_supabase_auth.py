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
        # Hết hạn ngoài leeway (30s) mới bị chối
        with pytest.raises(AuthError):
            security.verify_supabase_token(make_token(expires_in_seconds=-120))

    def test_accepts_token_issued_in_near_future(self, make_token):
        """Máy local chậm hơn Supabase vài giây: iat > giờ máy nhưng trong
        leeway → vẫn phải verify được (bug login xong bị đá về trang login)."""
        token = make_token(iat_offset_seconds=10)
        payload = security.verify_supabase_token(token)
        assert payload["sub"] == "sub-1"

    def test_rejects_token_issued_far_future(self, make_token):
        with pytest.raises(AuthError):
            security.verify_supabase_token(make_token(iat_offset_seconds=120))


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
        assert "not verified" in resp.json()["detail"]

    def test_accepts_token_without_email_verified_claim(self, client, make_token):
        """JWT Signing Keys mới của Supabase bỏ claim `email_verified` khỏi
        access token — token như vậy vẫn phải tạo user + login bình thường."""
        token = make_token(sub="sub-new-keys", email="newkeys@gmail.com", email_verified=None)
        resp = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200, resp.text
        assert resp.json()["email"] == "newkeys@gmail.com"

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


class TestUserPersistedInDatabase:
    """Yêu cầu nghiệp vụ: tài khoản đăng nhập phải nằm THẬT trong bảng users.

    Client gọi /auth/me ngay sau khi Supabase cấp phiên (lúc đăng ký và mỗi lần
    đăng nhập) — chính lời gọi đó phải INSERT/UPDATE row, không chỉ trả JSON.
    """

    def test_sign_in_creates_row(self, client, make_token, db_session_factory):
        token = make_token(sub="sub-persist", email="Persist@Gmail.com", name="Bền")
        resp = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200, resp.text

        with db_session_factory() as db:
            rows = db.query(User).all()
            assert len(rows) == 1
            assert rows[0].email == "persist@gmail.com"  # chuẩn hóa lowercase
            assert rows[0].supabase_id == "sub-persist"
            assert rows[0].name == "Bền"
            # Credit khởi tạo cho user mới vẫn được gán
            assert rows[0].credit_free > 0

    def test_repeated_sign_in_does_not_duplicate_rows(
        self, client, make_token, db_session_factory
    ):
        token = make_token(sub="sub-repeat", email="repeat@gmail.com")
        for _ in range(3):
            resp = client.get(
                "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
            )
            assert resp.status_code == 200, resp.text

        with db_session_factory() as db:
            assert db.query(User).filter(User.email == "repeat@gmail.com").count() == 1

    def test_profile_change_from_token_is_saved(
        self, client, make_token, db_session_factory
    ):
        first = make_token(sub="sub-name", email="name@gmail.com", name="Tên cũ")
        assert (
            client.get(
                "/api/v1/auth/me", headers={"Authorization": f"Bearer {first}"}
            ).status_code
            == 200
        )
        second = make_token(sub="sub-name", email="name@gmail.com", name="Tên mới")
        assert (
            client.get(
                "/api/v1/auth/me", headers={"Authorization": f"Bearer {second}"}
            ).status_code
            == 200
        )

        with db_session_factory() as db:
            user = db.query(User).one()
            assert user.name == "Tên mới"

    def test_rejected_token_does_not_create_row(
        self, client, make_token, db_session_factory
    ):
        """Token sai (khác audience) → 401 và KHÔNG có row rác trong DB."""
        bad = make_token(sub="sub-bad", email="bad@gmail.com", audience="anon")
        resp = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {bad}"})
        assert resp.status_code == 401

        with db_session_factory() as db:
            assert db.query(User).count() == 0


class TestUpdateDisplayName:
    """Màn "đặt tên" ngay sau lần đăng nhập đầu tiên (PATCH /auth/me).

    App dựa vào `name_chosen_at` để biết còn phải hỏi tên hay không: NULL =
    chưa đặt (hiện màn đặt tên), có giá trị = đã đặt (vào thẳng app chính).
    """

    def test_first_sign_in_asks_for_name_then_patch_saves_it(
        self, client, make_token, db_session_factory
    ):
        token = make_token(sub="sub-named", email="named@gmail.com", name="Tên Google")
        headers = {"Authorization": f"Bearer {token}"}

        # Lần đăng nhập đầu: Google có cho tên nhưng người dùng CHƯA chọn tên
        first = client.get("/api/v1/auth/me", headers=headers)
        assert first.status_code == 200, first.text
        assert first.json()["name"] == "Tên Google"
        assert first.json()["name_chosen_at"] is None

        # Đặt tên (dấu cách thừa ở hai đầu bị cắt)
        saved = client.patch("/api/v1/auth/me", json={"name": "  Hoàng  "}, headers=headers)
        assert saved.status_code == 200, saved.text
        assert saved.json()["name"] == "Hoàng"
        assert saved.json()["name_chosen_at"] is not None

        # Lần sau vào app không hỏi lại
        again = client.get("/api/v1/auth/me", headers=headers)
        assert again.json()["name"] == "Hoàng"
        assert again.json()["name_chosen_at"] is not None

        with db_session_factory() as db:
            user = db.query(User).one()
            assert user.name == "Hoàng"
            assert user.name_chosen_at is not None

    def test_later_google_token_does_not_overwrite_chosen_name(
        self, client, make_token
    ):
        """Google đổi tên profile sau này cũng không được ghi đè tên đã chọn."""
        chosen = make_token(sub="sub-own", email="own@gmail.com", name="Tên Google")
        client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {chosen}"})
        client.patch(
            "/api/v1/auth/me",
            json={"name": "Tên tự đặt"},
            headers={"Authorization": f"Bearer {chosen}"},
        )

        renamed_google = make_token(sub="sub-own", email="own@gmail.com", name="Tên Google mới")
        resp = client.get(
            "/api/v1/auth/me", headers={"Authorization": f"Bearer {renamed_google}"}
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["name"] == "Tên tự đặt"

    @pytest.mark.parametrize("blank", ["", "   "])
    def test_blank_name_rejected(self, client, make_token, db_session_factory, blank):
        token = make_token(sub="sub-blank", email="blank@gmail.com")
        headers = {"Authorization": f"Bearer {token}"}
        client.get("/api/v1/auth/me", headers=headers)

        resp = client.patch("/api/v1/auth/me", json={"name": blank}, headers=headers)
        assert resp.status_code == 422

        with db_session_factory() as db:
            assert db.query(User).one().name_chosen_at is None

    def test_requires_bearer_token(self, client):
        resp = client.patch("/api/v1/auth/me", json={"name": "Ai đó"})
        assert resp.status_code == 401

    def test_only_touches_current_user(self, client, make_token, db_session_factory):
        mine = make_token(sub="sub-mine", email="mine@gmail.com")
        other = make_token(sub="sub-other", email="other@gmail.com")
        for token in (mine, other):
            client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})

        client.patch(
            "/api/v1/auth/me",
            json={"name": "Của tôi"},
            headers={"Authorization": f"Bearer {mine}"},
        )

        with db_session_factory() as db:
            rows = {u.email: u for u in db.query(User).all()}
            assert rows["mine@gmail.com"].name == "Của tôi"
            assert rows["mine@gmail.com"].name_chosen_at is not None
            assert rows["other@gmail.com"].name is None
            assert rows["other@gmail.com"].name_chosen_at is None
