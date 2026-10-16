"""Fixture test: env bắt buộc set TRƯỚC khi import app; DB = SQLite in-memory (StaticPool).

Test suite chạy được mà không cần Postgres/Docker — chỉ test logic, không test driver.
"""

import os

os.environ.setdefault("JWT_SECRET", "test-secret-key-dai-it-nhat-32-ky-tu-0123456789")
os.environ.setdefault(
    "GOOGLE_CLIENT_IDS",
    "test-web-client-id.apps.googleusercontent.com,test-desktop-client-id.apps.googleusercontent.com",
)
os.environ.setdefault("ACCESS_TOKEN_MINUTES", "15")
os.environ.setdefault("REFRESH_TOKEN_DAYS", "30")
os.environ.setdefault("CORS_ORIGINS", "")
# Test phải tất định: KHÔNG phụ thuộc .env của máy dev (dev có thể bật dev-login).
# Ép (không setdefault) để test "dev login off by default" luôn đúng.
os.environ["ALLOW_DEV_LOGIN"] = "false"

from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401 — đăng ký model vào metadata
from app.core.google import GoogleIdentity
from app.db.base import Base
from app.db.session import get_db
from app.main import create_app


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
def client(db_session_factory) -> Iterator[TestClient]:
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


@pytest.fixture()
def make_identity() -> Callable[..., GoogleIdentity]:
    """Factory tạo GoogleIdentity giả — đã 'qua' bước verify Google."""

    def _make(
        google_sub: str = "g-sub-1",
        email: str = "user1@gmail.com",
        name: str | None = "Nguyễn Văn A",
        avatar_url: str | None = "https://lh3.googleusercontent.com/a.jpg",
    ) -> GoogleIdentity:
        return GoogleIdentity(
            google_sub=google_sub, email=email, name=name, avatar_url=avatar_url
        )

    return _make
