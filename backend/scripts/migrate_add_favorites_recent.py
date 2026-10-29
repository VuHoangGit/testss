"""Thêm cột `is_favorite` + `last_opened_at` cho bảng `documents` (chạy 1 lần).

DB đã có dữ liệu thật (SQLite local) nên KHÔNG drop/recreate: chỉ ALTER TABLE
ADD COLUMN khi cột còn thiếu. Idempotent — chạy lại không lỗi, không đụng dữ liệu cũ.

Chạy:  python scripts/migrate_add_favorites_recent.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import inspect, text  # noqa: E402

from app.db.session import engine  # noqa: E402

# Cột cần có: (tên, DDL điền theo model documents.py)
_COLUMNS: dict[str, str] = {
    "is_favorite": "ALTER TABLE documents ADD COLUMN is_favorite BOOLEAN NOT NULL DEFAULT 0",
    "last_opened_at": "ALTER TABLE documents ADD COLUMN last_opened_at DATETIME",
}


def main() -> int:
    existing = {col["name"] for col in inspect(engine).get_columns("documents")}
    added = 0
    with engine.begin() as conn:
        for name, ddl in _COLUMNS.items():
            if name not in existing:
                conn.execute(text(ddl))
                added += 1
                print(f"Da them cot documents.{name}")
    if added == 0:
        print("Cot is_favorite/last_opened_at da ton tai — khong lam gi them.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
