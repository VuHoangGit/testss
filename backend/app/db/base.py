"""Declarative base + kiểu cột dùng chung cho toàn bộ model."""

from datetime import UTC

from sqlalchemy import DateTime, types
from sqlalchemy.orm import DeclarativeBase


class UTCDateTime(types.TypeDecorator):
    """DateTime chuẩn hóa UTC 2 chiều.

    SQLite lưu datetime không kèm timezone → khi đọc ra là naive, so sánh với
    datetime.now(timezone.utc) (aware) sẽ nổ TypeError. Kiểu này gắn UTC khi
    đọc và quy về UTC khi ghi — nhất quán trên cả SQLite (test) và Postgres.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


class Base(DeclarativeBase):
    pass
