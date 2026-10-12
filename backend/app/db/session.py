"""Engine + session factory SQLAlchemy (sync) và dependency `get_db` cho FastAPI."""

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

# Engine tạo lúc import nhưng KHÔNG kết nối (lazy) — an toàn khi chạy test không có Postgres
engine = create_engine(get_settings().database_url, pool_pre_ping=True)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """Dependency: 1 session cho mỗi request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
