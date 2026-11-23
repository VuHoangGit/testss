"""Tạo bảng `document_shares` + `share_comments` cho DB đang chạy (chạy 1 lần).

Idempotent — bảng đã có thì create_all bỏ qua, không đụng dữ liệu thật (SRS
chỉ thị: script theo pattern script hiện có, KHÔNG drop/recreate).

Chạy:  python scripts/migrate_add_shares.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import inspect, text  # noqa: E402

from app.db.session import engine  # noqa: E402
from app.models.document_share import DocumentShare  # noqa: E402
from app.models.share_comment import ShareComment  # noqa: E402


def main() -> int:
    from app.db.base import Base

    Base.metadata.create_all(
        engine, tables=[DocumentShare.__table__, ShareComment.__table__]
    )
    # CSDL đã tạo bảng ở bản đầu: chỉ thêm cột còn thiếu, tuyệt đối không drop.
    with engine.begin() as connection:
        columns = {c["name"] for c in inspect(connection).get_columns("share_comments")}
        if "is_pinned" not in columns:
            connection.execute(
                text(
                    "ALTER TABLE share_comments ADD COLUMN is_pinned BOOLEAN NOT NULL DEFAULT TRUE"
                )
            )
    print("Bang document_shares + share_comments: da dam bao ton tai (idempotent)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
