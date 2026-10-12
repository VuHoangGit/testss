"""Test app.core.security: JWT roundtrip/hết hạn/sai secret/claim thiếu + refresh token/hash."""

import uuid
from datetime import UTC, datetime, timedelta

import jwt as pyjwt
import pytest

from app.core.config import Settings
from app.core.security import (
    AuthError,
    create_access_token,
    decode_access_token,
    generate_refresh_token,
    hash_refresh_token,
)

USER_ID = uuid.uuid4()
SESSION_ID = uuid.uuid4()


def _settings(secret: str = "du-mot-secret-32-ky-tu-tro-len-0123456789") -> Settings:
    return Settings(jwt_secret=secret, google_client_ids="client-a")


def test_access_token_roundtrip():
    token = create_access_token(
        USER_ID,
        SESSION_ID,
        email="a@gmail.com",
        name="Nguyễn Văn A",
        settings=_settings(),
    )
    payload = decode_access_token(token, settings=_settings())
    assert payload["sub"] == str(USER_ID)
    assert payload["sid"] == str(SESSION_ID)
    assert payload["type"] == "access"
    assert payload["iss"] == "docuvault"
    assert payload["email"] == "a@gmail.com"  # client khôi phục phiên offline từ claim
    assert payload["name"] == "Nguyễn Văn A"


def test_expired_token_rejected():
    past = datetime.now(UTC) - timedelta(hours=1)
    token = create_access_token(USER_ID, SESSION_ID, settings=_settings(), now=past)
    with pytest.raises(AuthError):
        decode_access_token(token, settings=_settings())


def test_wrong_secret_rejected():
    token = create_access_token(
        USER_ID, SESSION_ID, settings=_settings("secret-A-32-ky-tu-aaaa-aaaaaaaaaa")
    )
    with pytest.raises(AuthError):
        decode_access_token(token, settings=_settings("secret-B-32-ky-tu-bbbb-bbbbbbbbbb"))


def test_token_signed_by_other_key_rejected():
    # EC-34: client tự ký token giả → chữ ký không khớp → chặn
    forged = pyjwt.encode(
        {"sub": str(USER_ID), "sid": str(SESSION_ID), "type": "access", "exp": 9999999999},
        "khoa-gia-cua-hacker-dai-hon-32-bytes",
        algorithm="HS256",
    )
    with pytest.raises(AuthError):
        decode_access_token(forged, settings=_settings())


def test_refresh_type_token_rejected_as_access():
    # Token có type khác "access" không được dùng làm access
    settings = _settings()
    other = pyjwt.encode(
        {"sub": str(USER_ID), "sid": str(SESSION_ID), "type": "refresh", "exp": 9999999999},
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    with pytest.raises(AuthError):
        decode_access_token(other, settings=settings)


def test_missing_claims_rejected():
    settings = _settings()
    no_sub = pyjwt.encode(
        {"sid": str(SESSION_ID), "type": "access", "exp": 9999999999},
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    with pytest.raises(AuthError):
        decode_access_token(no_sub, settings=settings)


def test_generate_refresh_token_256bit_unique():
    tokens = {generate_refresh_token() for _ in range(100)}
    assert len(tokens) == 100  # không trùng
    # token_urlsafe(32) → 43 ký tự base64url ≈ 256-bit entropy
    assert all(len(t) == 43 for t in tokens)


def test_hash_refresh_token_known_vector():
    assert (
        hash_refresh_token("abc")
        == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )


def test_hash_is_deterministic_and_differs_per_token():
    t1, t2 = generate_refresh_token(), generate_refresh_token()
    assert hash_refresh_token(t1) == hash_refresh_token(t1)
    assert hash_refresh_token(t1) != hash_refresh_token(t2)
