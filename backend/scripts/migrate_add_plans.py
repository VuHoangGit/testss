"""Switch to the subscription model: plan columns on users, unlimited +
plan_code on payments, seed the 4 new monthly plans (run once, idempotent).

The dev DB holds real data (local SQLite), so NO drop/recreate: only ALTER
TABLE ADD COLUMN when a column is missing; legacy packages P50…P10000 get
active=False but old orders/credits read back unchanged (orders with an empty
plan_code still add credit_purchased via the legacy webhook path). Re-running
is safe and touches nothing extra.

Steps:
a) ALTER users ADD plan_code/plan_expires_at; ALTER pricing_packages ADD
   unlimited; ALTER payment_orders ADD plan_code (skip existing columns).
b) UPDATE users SET plan_code='FREE' WHERE plan_code IS NULL.
c) Deactivate legacy packages + seed the 4 new plans via ensure_pricing_seed
   (UPDATE by code).
d) Print the result of each step.

Run:  python scripts/migrate_add_plans.py
"""

import sys
from pathlib import Path

# Windows console defaults to cp1252 — cannot print Vietnamese chars; force UTF-8
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import inspect, text  # noqa: E402

from app.db.session import SessionLocal, engine  # noqa: E402

# New columns to add — SQLite ALTER TABLE ADD COLUMN does not support NOT NULL
# without DEFAULT, so the DDL covers all existing rows immediately.
_TABLE_COLUMNS: dict[str, dict[str, str]] = {
    "users": {
        "plan_code": "ALTER TABLE users ADD COLUMN plan_code VARCHAR(16) "
        "NOT NULL DEFAULT 'FREE'",
        "plan_expires_at": "ALTER TABLE users ADD COLUMN plan_expires_at DATETIME NULL",
    },
    "pricing_packages": {
        "unlimited": "ALTER TABLE pricing_packages ADD COLUMN unlimited BOOLEAN "
        "NOT NULL DEFAULT 0",
    },
    "payment_orders": {
        "plan_code": "ALTER TABLE payment_orders ADD COLUMN plan_code VARCHAR(16) "
        "NOT NULL DEFAULT ''",
    },
}


def main() -> int:
    # (a) Add missing columns on the 3 tables
    inspector = inspect(engine)
    for table, columns in _TABLE_COLUMNS.items():
        existing = {col["name"] for col in inspector.get_columns(table)}
        for name, ddl in columns.items():
            if name in existing:
                print(f"Column {table}.{name} already exists — skip ALTER TABLE")
                continue
            with engine.begin() as conn:
                conn.execute(text(ddl))
            print(f"Added column {table}.{name}")

    with engine.begin() as conn:
        # (b) Default existing users to the FREE plan
        result = conn.execute(
            text("UPDATE users SET plan_code = 'FREE' WHERE plan_code IS NULL")
        )
        print(f"users.plan_code='FREE': {result.rowcount} rows updated")

    # (c) Deactivate legacy packages + seed/align the 4 subscription plans
    from app.services import payment_service

    with SessionLocal() as db:
        legacy_active = (
            db.query(payment_service.PricingPackage)
            .filter(
                payment_service.PricingPackage.code.in_(
                    payment_service.LEGACY_PACKAGE_CODES
                ),
                payment_service.PricingPackage.active,
            )
            .count()
        )
        payment_service.ensure_pricing_seed(db)
    print(f"Legacy packages still active: {legacy_active} (deactivated by seed)")
    print("Seed 4 subscription plans FREE/PLUS/PRO/MAX: done (idempotent)")

    # (d) Print the final state for verification
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT code, name, price_vnd, credits, unlimited, active, sort_order "
                "FROM pricing_packages ORDER BY sort_order"
            )
        )
        print("--- pricing_packages after migration ---")
        for row in rows:
            print(f"  {row[0]:6} | {row[1]:22} | {row[2]:>7} VND | "
                  f"{row[3]:>6} cr | unlimited={row[4]} | active={row[5]} | sort={row[6]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
