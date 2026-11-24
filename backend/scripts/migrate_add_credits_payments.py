"""Thêm cột credit cho `users` + bảng pricing_packages/payment_orders (chạy 1 lần).

DB đã có dữ liệu thật (SQLite local) nên KHÔNG drop/recreate: chỉ ALTER TABLE
ADD COLUMN khi cột còn thiếu; bảng mới tạo bằng metadata (CREATE IF NOT EXISTS);
seed 3 gói credit theo code (idempotent). Chạy lại không lỗi, không đụng dữ liệu cũ.

Chạy:  python scripts/migrate_add_credits_payments.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import inspect, text  # noqa: E402

from app.db.session import engine  # noqa: E402
from app.models.payment import PaymentOrder, PricingPackage  # noqa: E402
from app.services import payment_service  # noqa: E402

# Cột credit mới trên bảng users — user cũ được tặng đúng 500 free kỳ này,
# credit_period rỗng → lần đọc/charge đầu tiên tự ghi kỳ hiện tại.
_USER_COLUMNS: dict[str, str] = {
    "credit_free": "ALTER TABLE users ADD COLUMN credit_free INTEGER NOT NULL DEFAULT 500",
    "credit_purchased": "ALTER TABLE users ADD COLUMN credit_purchased INTEGER NOT NULL DEFAULT 0",
    "credit_period": "ALTER TABLE users ADD COLUMN credit_period VARCHAR(7) NOT NULL DEFAULT ''",
}


def main() -> int:
    from app.db.base import Base

    added = 0
    existing = {col["name"] for col in inspect(engine).get_columns("users")}
    with engine.begin() as conn:
        for name, ddl in _USER_COLUMNS.items():
            if name not in existing:
                conn.execute(text(ddl))
                added += 1
                print(f"Da them cot users.{name}")

    # Bảng mới (pricing_packages, payment_orders) — CREATE TABLE IF NOT EXISTS
    Base.metadata.create_all(engine, tables=[PricingPackage.__table__, PaymentOrder.__table__])
    print("Bang pricing_packages/payment_orders: da dam bao ton tai")

    # Seed 3 gói nạp (P1000/P2500/P10000) nếu thiếu
    from app.db.session import SessionLocal

    with SessionLocal() as db:
        payment_service.ensure_pricing_seed(db)
    print("Seed goi credit: xong (idempotent)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
