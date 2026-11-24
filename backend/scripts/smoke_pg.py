"""Smoke test the full order + webhook flow against Supabase Postgres.

Creates a throwaway user + PLUS order, simulates the SePay webhook, checks
the plan was applied, verifies the replay guard, then deletes both rows.
Run:  python scripts/smoke_pg.py
"""

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services import payment_service  # noqa: E402


def main() -> int:
    db = SessionLocal()
    u = User(
        email=f"smoke-{uuid.uuid4().hex[:6]}@test.local",
        name="Smoke PG",
        credit_free=300,
        credit_purchased=0,
    )
    db.add(u)
    db.commit()
    print("user created:", u.id, type(u.id).__name__)

    order = payment_service.create_order(db, u, "PLUS")
    print("order:", order.order_code, order.amount_vnd, order.status)

    payload = {
        "content": f"CT tu 0987 toi VU MINH HOANG. SUBSCRIBE {order.order_code}",
        "transferAmount": 50000,
        "transferType": "in",
        "transactionNumber": "FT" + uuid.uuid4().hex[:10],
        "accountNumber": get_settings().sepay_bank_account,
    }
    print("webhook:", payment_service.process_sepay_webhook(db, payload))

    db.refresh(u)
    db.refresh(order)
    print(
        "AFTER: order.status =", order.status,
        "| user plan =", u.plan_code,
        "| expires =", u.plan_expires_at,
        "| free credits =", u.credit_free,
    )

    print("replay:", payment_service.process_sepay_webhook(db, payload))

    db.delete(order)
    db.delete(u)
    db.commit()
    print("cleaned up")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
