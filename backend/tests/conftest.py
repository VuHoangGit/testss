"""Fixture test: env đặt TRƯỚC khi import app; DB = SQLite in-memory (StaticPool).

Test suite chạy được mà không cần Postgres/Supabase thật: access token Supabase
được KÝ THẬT bằng cặp RSA sinh trong test, và JWKS client giả gắn vào cache
của app.core.security — phần verify chạy đúng code production, chỉ bỏ mạng.
"""

import os

os.environ.setdefault("SUPABASE_URL", "https://test-project.supabase.co")
os.environ.setdefault("CORS_ORIGINS", "")

from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401 — đăng ký model vào metadata
from app.core import security
from app.db.base import Base
from app.db.session import get_db
from app.main import create_app

_TEST_SUPABASE_URL = "https://test-project.supabase.co"
_TEST_ISSUER = f"{_TEST_SUPABASE_URL}/auth/v1"


class _FakeJWKClient:
    """Thay PyJWKClient: luôn trả signing key của test, không gọi mạng."""

    def __init__(self, key: jwt.PyJWK) -> None:
        self._key = key

    def get_signing_key_from_jwt(self, token: str) -> jwt.PyJWK:
        return self._key


@pytest.fixture(scope="session")
def _signing_key():
    """Cặp RSA 1 lần cho cả suite; gắn client giả vào cache JWKS của security."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_jwk = jwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key(), as_dict=True)
    security._jwk_clients[_TEST_SUPABASE_URL] = _FakeJWKClient(
        jwt.PyJWK(public_jwk, algorithm="RS256")
    )
    return private_pem


@pytest.fixture()
def make_token(_signing_key) -> Callable[..., str]:
    """Factory sinh access token Supabase giả (chữ ký RSA thật của test)."""

    def _make(
        sub: str = "sub-1",
        email: str = "user1@example.com",
        *,
        # None = bỏ claim (token JWT Signing Keys mới của Supabase không có)
        email_verified: bool | None = True,
        name: str | None = None,
        avatar_url: str | None = None,
        expires_in_seconds: int = 3600,
        # >0: iat nằm trong tương lai (giả lập máy local chậm hơn Supabase)
        iat_offset_seconds: int = 0,
        issuer: str = _TEST_ISSUER,
        audience: str = "authenticated",
    ) -> str:
        now = datetime.now(UTC)
        metadata: dict[str, Any] = {}
        if name is not None:
            metadata["full_name"] = name
        if avatar_url is not None:
            metadata["avatar_url"] = avatar_url
        payload = {
            "sub": sub,
            "iss": issuer,
            "aud": audience,
            "iat": int(now.timestamp()) + iat_offset_seconds,
            "exp": int((now + timedelta(seconds=expires_in_seconds)).timestamp()),
            "email": email,
            "user_metadata": metadata,
        }
        if email_verified is not None:
            payload["email_verified"] = email_verified
        return jwt.encode(payload, _signing_key, algorithm="RS256")

    return _make


@pytest.fixture()
def db_engine():
    # StaticPool: 1 connection duy nhất dùng chung → các session thấy cùng 1 DB ":memory:"
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture()
def db_session_factory(db_engine) -> sessionmaker[Session]:
    return sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)


@pytest.fixture()
def client(db_session_factory, _signing_key) -> Iterator[TestClient]:
    app = create_app()

    def override_get_db() -> Iterator[Session]:
        db = db_session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
