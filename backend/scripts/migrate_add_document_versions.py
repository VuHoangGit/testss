"""Tạo bảng `document_versions` cho DB đang chạy (chạy 1 lần).

Idempotent — bảng đã có thì create_all bỏ qua, không đụng dữ liệu thật. DB đang
có dữ liệu thật nên KHÔNG drop/recreate.

Chạy:  python scripts/migrate_add_document_versions.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.session import engine  # noqa: E402
from app.models.document_version import DocumentVersion  # noqa: E402


def main() -> int:
    from app.db.base import Base

    Base.metadata.create_all(engine, tables=[DocumentVersion.__table__])
    print("Bang document_versions: da dam bao ton tai (idempotent)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
