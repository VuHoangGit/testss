"""Test đăng ký/đăng nhập email + mật khẩu (Sprint 2.5)."""

from sqlalchemy.orm import Session

from app.core.google import GoogleIdentity
from app.core.passwords import hash_password, verify_password
from app.services import auth_service
from app.services.auth_service import EmailAlreadyRegisteredError


class TestPasswordHashing:
    def test_hash_va_verify_dung(self) -> None:
        stored = hash_password("123456")
        assert stored.startswith("pbkdf2_sha256$")
        assert verify_password("123456", stored)

    def test_sai_mat_khau(self) -> None:
        stored = hash_password("123456")
        assert not verify_password("654321", stored)

    def test_hash_lan_nua_khac_salt(self) -> None:
        assert hash_password("123456") != hash_password("123456")

    def test_sai_format_tra_ve_false_khong_nem(self) -> None:
        assert not verify_password("123456", "khong-phai-hash")


class TestRegisterService:
    def test_register_moi_va_dang_nhap_duoc(self, db_session_factory) -> None:
        with db_session_factory() as db:
            user = auth_service.register_user(db, "Hoang@gmail.com", "123456", None)
            assert user.google_sub is None
            assert user.email == "hoang@gmail.com"  # chuẩn hóa lowercase

            authed, session, refresh_token = auth_service.login_with_password(
                db, "hoang@gmail.com", "123456", None
            )
            assert authed.id == user.id
            assert refresh_token
            assert session.user_id == user.id

    def test_email_da_dang_ky(self, db_session_factory) -> None:
        with db_session_factory() as db:
            auth_service.register_user(db, "hoang@gmail.com", "123456", None)
            try:
                auth_service.register_user(db, "hoang@gmail.com", "999999", None)
            except EmailAlreadyRegisteredError:
                pass
            else:
                raise AssertionError("Phải ném EmailAlreadyRegisteredError")

    def test_user_google_chua_co_mat_khau_duoc_gan_mat_khau(self, db_session_factory) -> None:
        with db_session_factory() as db:
            google_user = auth_service.upsert_user_by_google(
                db,
                GoogleIdentity(
                    google_sub="sub-1", email="hoang@gmail.com", name="Hoàng", avatar_url=None
                ),
            )
            merged = auth_service.register_user(db, "hoang@gmail.com", "123456", None)
            assert merged.id == google_user.id
            assert merged.password_hash is not None
            assert Session.object_session(merged) is db


class TestRegisterApi:
    def test_register_201_roi_login_200(self, client) -> None:
        res = client.post(
            "/api/v1/auth/register",
            json={"email": "hoang@gmail.com", "password": "123456", "name": "Hoàng"},
        )
        assert res.status_code == 201, res.text
        assert res.json()["email"] == "hoang@gmail.com"

        login = client.post(
            "/api/v1/auth/login",
            json={"email": "hoang@gmail.com", "password": "123456"},
        )
        assert login.status_code == 200, login.text
        body = login.json()
        assert body["access_token"] and body["refresh_token"]
        assert body["user"]["email"] == "hoang@gmail.com"

    def test_register_trung_email_409(self, client) -> None:
        payload = {"email": "hoang@gmail.com", "password": "123456"}
        assert client.post("/api/v1/auth/register", json=payload).status_code == 201
        dup = client.post("/api/v1/auth/register", json=payload)
        assert dup.status_code == 409
        assert dup.json()["detail"] == "Email đã được đăng ký"

    def test_mat_khau_qua_ngan_422(self, client) -> None:
        res = client.post(
            "/api/v1/auth/register", json={"email": "hoang@gmail.com", "password": "12345"}
        )
        assert res.status_code == 422

    def test_email_sai_dinh_dang_422(self, client) -> None:
        res = client.post(
            "/api/v1/auth/register", json={"email": "khong-phai-email", "password": "123456"}
        )
        assert res.status_code == 422

    def test_login_sai_mat_khau_401(self, client) -> None:
        client.post(
            "/api/v1/auth/register", json={"email": "hoang@gmail.com", "password": "123456"}
        )
        res = client.post(
            "/api/v1/auth/login", json={"email": "hoang@gmail.com", "password": "999999"}
        )
        assert res.status_code == 401
        assert res.json()["detail"] == "Email hoặc mật khẩu không đúng"

    def test_login_email_chua_dang_ky_401(self, client) -> None:
        res = client.post(
            "/api/v1/auth/login", json={"email":"nobody@gmail.com", "password": "123456"}
        )
        assert res.status_code == 401
