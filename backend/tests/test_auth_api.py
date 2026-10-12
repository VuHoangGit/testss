"""Test API /api/v1/auth/*: login Google, refresh rotation, logout, me, health.

verify_google_id_token được patch ở lớp router (không gọi Google thật).
"""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from app.core.google import GoogleIdentity
from app.core.security import AuthError, hash_refresh_token
from app.models.session import UserSession
from app.models.user import User

FAKE_ID_TOKEN = "fake-id-token-do-google-cap-du-dai-20-ky-tu"
DEVICE_INFO = {"platform": "android", "model": "Pixel 8"}


def _login(client, monkeypatch, identity: GoogleIdentity, device_info=None):
    monkeypatch.setattr("app.api.v1.auth.verify_google_id_token", lambda token: identity)
    return client.post(
        "/api/v1/auth/google",
        json={"id_token": FAKE_ID_TOKEN, "device_info": device_info or DEVICE_INFO},
    )


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_login_happy_path(client, monkeypatch, make_identity, db_session_factory):
    resp = _login(client, monkeypatch, make_identity())
    assert resp.status_code == 200
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == 15 * 60
    assert body["user"]["email"] == "user1@gmail.com"
    assert body["access_token"] and body["refresh_token"]

    with db_session_factory() as db:
        assert db.scalar(select(func.count()).select_from(User)) == 1
        session = db.scalars(select(UserSession)).one()
        assert session.revoked_at is None
        # DB chỉ lưu hash, không lưu plaintext (EC: security)
        assert session.refresh_token_hash == hash_refresh_token(body["refresh_token"])
        assert session.device_info == DEVICE_INFO


def test_login_twice_same_google_sub_no_duplicate_user(
    client, monkeypatch, make_identity, db_session_factory
):  # EC-27 + EC-36
    _login(client, monkeypatch, make_identity(email="cu@gmail.com"))
    resp = _login(client, monkeypatch, make_identity(email="moi@gmail.com"))
    assert resp.status_code == 200
    assert resp.json()["user"]["email"] == "moi@gmail.com"  # cập nhật theo Google

    with db_session_factory() as db:
        assert db.scalar(select(func.count()).select_from(User)) == 1
        assert db.scalar(select(func.count()).select_from(UserSession)) == 2  # mỗi login 1 session


def test_login_invalid_google_token_rejected_no_user_created(
    client, monkeypatch, db_session_factory
):  # EC-01/02/03
    def _raise(token: str) -> GoogleIdentity:
        raise AuthError("Token Google không hợp lệ hoặc đã hết hạn")

    monkeypatch.setattr("app.api.v1.auth.verify_google_id_token", _raise)
    resp = client.post("/api/v1/auth/google", json={"id_token": FAKE_ID_TOKEN})
    assert resp.status_code == 401
    with db_session_factory() as db:
        assert db.scalar(select(func.count()).select_from(User)) == 0


def test_login_rejects_short_id_token(client):  # validate input ở boundary
    resp = client.post("/api/v1/auth/google", json={"id_token": "ngan"})
    assert resp.status_code == 422


def test_me_with_valid_access_token(client, monkeypatch, make_identity):
    body = _login(client, monkeypatch, make_identity()).json()
    resp = client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"}
    )
    assert resp.status_code == 200
    assert resp.json()["email"] == "user1@gmail.com"


def test_me_without_token_or_garbage_token_rejected(client):
    assert client.get("/api/v1/auth/me").status_code == 401
    assert (
        client.get(
            "/api/v1/auth/me", headers={"Authorization": "Bearer khong-phai-jwt"}
        ).status_code
        == 401
    )


def test_refresh_rotates_session_and_kills_old_token(
    client, monkeypatch, make_identity, db_session_factory
):  # EC-11 nghiêm ngặt
    login_body = _login(client, monkeypatch, make_identity()).json()
    old_refresh = login_body["refresh_token"]

    resp = client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
    assert resp.status_code == 200
    new = resp.json()
    assert new["access_token"] != login_body["access_token"]
    assert new["refresh_token"] != old_refresh

    # Token cũ đã revoke → reuse bị từ chối
    reuse = client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
    assert reuse.status_code == 401

    with db_session_factory() as db:
        assert db.scalar(select(func.count()).select_from(UserSession)) == 2
        revoked = db.scalars(
            select(UserSession).where(UserSession.revoked_at.is_not(None))
        ).all()
        assert len(revoked) == 1


def test_refresh_unknown_token_rejected(client):
    resp = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": "refresh-token-khong-ton-tai-trong-db"},
    )
    assert resp.status_code == 401


def test_refresh_expired_session_rejected(
    client, monkeypatch, make_identity, db_session_factory
):  # EC-12
    login_body = _login(client, monkeypatch, make_identity()).json()
    with db_session_factory() as db:
        session = db.scalars(select(UserSession)).one()
        session.expires_at = datetime.now(UTC) - timedelta(days=1)
        db.commit()

    resp = client.post(
        "/api/v1/auth/refresh", json={"refresh_token": login_body["refresh_token"]}
    )
    assert resp.status_code == 401
    assert "hết hạn" in resp.json()["detail"]


def test_logout_revokes_session_and_me_rejected_afterwards(
    client, monkeypatch, make_identity, db_session_factory
):  # EC-18/29
    body = _login(client, monkeypatch, make_identity()).json()
    auth_header = {"Authorization": f"Bearer {body['access_token']}"}

    resp = client.post("/api/v1/auth/logout", headers=auth_header)
    assert resp.status_code == 200

    # Access token còn hạn về mặt JWT nhưng session đã revoke → 401
    assert client.get("/api/v1/auth/me", headers=auth_header).status_code == 401

    with db_session_factory() as db:
        session = db.scalars(select(UserSession)).one()
        assert session.revoked_at is not None


def test_logout_service_is_idempotent(db_session_factory):  # EC-20
    from app.services.auth_service import logout_session

    with db_session_factory() as db:
        user = User(google_sub="g-logout", email="lo@gmail.com")
        db.add(user)
        db.flush()
        session = UserSession(
            user_id=user.id,
            refresh_token_hash=uuid.uuid4().hex,
            expires_at=datetime.now(UTC) + timedelta(days=1),
        )
        db.add(session)
        db.commit()

        logout_session(db, session.id)
        db.commit()
        first_revoked = db.scalar(
            select(UserSession.revoked_at).where(UserSession.id == session.id)
        )
        assert first_revoked is not None

        # Gọi lần 2: WHERE revoked_at IS NULL → không đổi giá trị, không lỗi
        logout_session(db, session.id)
        db.commit()
        assert (
            db.scalar(select(UserSession.revoked_at).where(UserSession.id == session.id))
            == first_revoked
        )


def test_login_truncates_oversized_device_info(
    client, monkeypatch, make_identity, db_session_factory
):  # EC-32
    huge = {f"key_{i}": "x" * 500 for i in range(30)}
    resp = _login(client, monkeypatch, make_identity(), device_info=huge)
    assert resp.status_code == 200

    with db_session_factory() as db:
        session = db.scalars(select(UserSession)).one()
        stored = session.device_info
        assert stored is not None
        assert len(stored) <= 20
        assert all(len(v) <= 300 for v in stored.values())


def test_me_session_revoked_directly_in_db(client, monkeypatch, make_identity, db_session_factory):
    body = _login(client, monkeypatch, make_identity()).json()
    with db_session_factory() as db:
        session = db.scalars(select(UserSession)).one()
        session.revoked_at = datetime.now(UTC)
        db.commit()

    resp = client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"}
    )
    assert resp.status_code == 401
    assert "thu hồi" in resp.json()["detail"]
