"""Subscription order creation + SePay webhook matching (idempotent, replay-safe)."""

import logging
import re
import secrets
from datetime import UTC, datetime, timedelta
from urllib.parse import quote_plus

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.payment import PaymentOrder, PricingPackage
from app.models.user import User

logger = logging.getLogger(__name__)

# Bỏ I/1/O/0... dễ đọc nhầm khi người dùng gõ nội dung chuyển khoản
_CODE_ALPHABET = "ABCDEFGHJKLMNPRTUVWXY34679"

# Default subscription plans — seeded idempotently by code at startup and
# migration. List order is `sort_order` (top to bottom on the pricing screen).
# FREE is active so it shows on the pricing screen but is NOT purchasable —
# create_order rejects it separately (it is the default plan).
DEFAULT_PACKAGES: list[dict[str, object]] = [
    {"code": "FREE", "name": "Free", "price_vnd": 0, "credits": 300,
     "badge": None, "active": True, "unlimited": False},
    {"code": "PLUS", "name": "Plus", "price_vnd": 50_000, "credits": 1_000,
     "badge": None, "active": True, "unlimited": False},
    {"code": "PRO", "name": "Pro", "price_vnd": 100_000, "credits": 2_500,
     "badge": "Most popular", "active": True, "unlimited": False},
    {"code": "MAX", "name": "Max", "price_vnd": 300_000, "credits": 10_000,
     "badge": None, "active": True, "unlimited": True},
]

# Legacy one-time credit packages — migration sets active=False; historical
# order data still reads back unchanged.
LEGACY_PACKAGE_CODES = ("P50", "P200", "P550", "P1000", "P1250", "P2500", "P3000", "P10000")


def ensure_pricing_seed(db: Session) -> None:
    """Insert/align subscription plans by code (idempotent).

    UPDATE by code: price/quota/badge/unlimited always sync back to the source
    of truth (changing a price means editing DEFAULT_PACKAGES + re-running the
    migration, no manual DB surgery). Legacy credit packages (P…) get
    deactivated so they are no longer sold, while old order rows stay intact.
    """
    for i, pkg in enumerate(DEFAULT_PACKAGES):
        row = db.scalar(select(PricingPackage).where(PricingPackage.code == pkg["code"]))
        if row is None:
            db.add(
                PricingPackage(
                    code=str(pkg["code"]),
                    name=str(pkg["name"]),
                    price_vnd=int(pkg["price_vnd"]),  # type: ignore[arg-type]
                    credits=int(pkg["credits"]),  # type: ignore[arg-type]
                    badge=pkg["badge"] if isinstance(pkg["badge"], str) else None,  # type: ignore[arg-type]
                    active=bool(pkg["active"]),  # type: ignore[arg-type]
                    unlimited=bool(pkg["unlimited"]),  # type: ignore[arg-type]
                    sort_order=i,
                )
            )
            continue
        row.name = str(pkg["name"])
        row.price_vnd = int(pkg["price_vnd"])  # type: ignore[arg-type]
        row.credits = int(pkg["credits"])  # type: ignore[arg-type]
        row.badge = pkg["badge"] if isinstance(pkg["badge"], str) else None  # type: ignore[arg-type]
        row.active = bool(pkg["active"])  # type: ignore[arg-type]
        row.unlimited = bool(pkg["unlimited"])  # type: ignore[arg-type]
        row.sort_order = i
    # Deactivate legacy one-time packages still active (idempotent re-runs)
    for row in db.scalars(
        select(PricingPackage).where(PricingPackage.code.in_(LEGACY_PACKAGE_CODES))
    ):
        if row.active:
            row.active = False
    db.commit()


def list_packages(db: Session) -> list[PricingPackage]:
    ensure_pricing_seed(db)
    return list(
        db.scalars(
            select(PricingPackage)
            .where(PricingPackage.active)
            .order_by(PricingPackage.sort_order, PricingPackage.price_vnd)
        )
    )


def get_package(db: Session, code: str) -> PricingPackage | None:
    return db.scalar(select(PricingPackage).where(PricingPackage.code == code))


def _new_order_code(db: Session) -> str:
    """Generate a unique "DV" + 6-char order code (retries on rare clashes)."""
    for _ in range(10):
        code = "DV" + "".join(secrets.choice(_CODE_ALPHABET) for _ in range(6))
        taken = db.scalar(select(PaymentOrder).where(PaymentOrder.order_code == code))
        if taken is None:
            return code
    raise RuntimeError("Could not generate a unique order code")


# SePay's own QR image service — returns PNG (img.vietqr.io only returns SVG,
# which Flutter `Image.network` cannot render, so it is not usable).
QR_IMAGE_BASE_URL = "https://qr.sepay.vn/img"


def build_qr_url(amount_vnd: int, transfer_content: str) -> str | None:
    """Bank-transfer QR image URL (PNG) when the receiving account is set.

    Returns None when `SEPAY_BANK_ACCOUNT` is not configured — the UI then
    shows the transfer details as text only.
    """
    settings = get_settings()
    account = settings.sepay_bank_account.strip()
    if not account:
        return None
    return (
        f"{QR_IMAGE_BASE_URL}"
        f"?acc={quote_plus(account)}"
        f"&bank={quote_plus(settings.sepay_bank_bin.strip())}"
        f"&amount={amount_vnd}"
        f"&des={quote_plus(transfer_content)}"
        "&template=compact"
    )


def create_order(db: Session, user: User, package_code: str) -> PaymentOrder:
    ensure_pricing_seed(db)
    if package_code.upper() == "FREE":
        raise PackageNotFoundError("The Free plan is default — nothing to buy")
    package = get_package(db, package_code.upper())
    if package is None or not package.active:
        raise PackageNotFoundError(f"Package not found: {package_code}")
    code = _new_order_code(db)
    content = f"SUBSCRIBE {code}"
    order = PaymentOrder(
        user_id=user.id,
        package_id=package.id,
        plan_code=package.code,
        order_code=code,
        amount_vnd=package.price_vnd,
        credits=package.credits,
        transfer_content=content,
        qr_url=build_qr_url(package.price_vnd, content),
    )
    db.add(order)
    db.commit()
    return order


def get_order(db: Session, order_id, user: User) -> PaymentOrder | None:
    order = db.get(PaymentOrder, order_id)
    if order is None or order.user_id != user.id:
        return None
    return order


def list_orders(db: Session, user: User, limit: int = 50) -> list[PaymentOrder]:
    return list(
        db.scalars(
            select(PaymentOrder)
            .where(PaymentOrder.user_id == user.id)
            .order_by(PaymentOrder.created_at.desc())
            .limit(limit)
        )
    )


class PackageNotFoundError(Exception):
    """Package code does not exist or is deactivated."""


def _apply_plan_to_user(user: User, order: PaymentOrder) -> None:
    """Activate the plan on the user once the webhook confirms payment.

    Early renewal while the plan is still active: new expiry = max(now, current
    expiry) + 30 days — no leftover days are lost. The monthly quota resets to
    the new plan's quota. Legacy credit orders (empty plan_code, created before
    the migration) still add to credit_purchased so old sales data keeps its
    original meaning.
    """
    plan = order.plan_code or ""
    if plan not in {"PLUS", "PRO", "MAX"}:
        user.credit_purchased += order.credits
        return
    from app.services.credit_service import plan_quota

    now = datetime.now(UTC)
    # Stack days only when the user already holds the same plan; buying a
    # different plan starts a fresh window from now (no stacked benefits).
    if user.plan_code == plan and user.plan_expires_at is not None:
        current_expiry = user.plan_expires_at
        if current_expiry.tzinfo is None:
            current_expiry = current_expiry.replace(tzinfo=UTC)
        base = max(now, current_expiry)
    else:
        base = now
    user.plan_code = plan
    user.plan_expires_at = base + timedelta(days=get_settings().plan_period_days)
    # The new monthly quota applies immediately within the current period:
    # overwrite the quota and stamp the current period so
    # ensure_monthly_refresh does not reset it again this month.
    user.credit_free = plan_quota(plan)
    user.credit_period = now.strftime("%Y-%m")


def process_sepay_webhook(db: Session, payload: dict) -> str:
    """Match an incoming bank transaction against a pending order.

    Always returns a result description for the endpoint to log; every
    non-matching case (no order code / wrong amount / already processed) is
    safe — responds 2xx to SePay without granting anything.

    Two replay guards: (1) the order must still be pending; (2) UNIQUE
    sepay_transaction_id — a SePay replay of an old transaction hits an
    IntegrityError.
    """
    content = str(payload.get("content") or "")
    try:
        amount = int(payload.get("transferAmount") or 0)
    except (TypeError, ValueError):
        amount = 0
    # SePay reports both incoming and outgoing transfers. Only INCOMING money
    # grants anything — otherwise an outgoing transfer whose content happens
    # to contain an order code would be mistaken for payment.
    transfer_type = str(payload.get("transferType") or "in").strip().lower()
    if transfer_type != "in":
        return f"ignored: transferType={transfer_type} (not money in)"
    # Match the receiving account: when SEPAY_BANK_ACCOUNT is configured and
    # the payload carries `accountNumber`, they must match — blocks a leaked
    # secret being used to inject fake transactions for another account.
    # Payloads without the field are accepted (some SePay webhook configs
    # omit it).
    configured_account = get_settings().sepay_bank_account.strip()
    account_number = str(payload.get("accountNumber") or "").strip()
    if configured_account and account_number and account_number != configured_account:
        return f"ignored: accountNumber {account_number} is not the receiving account"
    match = re.search(r"DV[A-Z0-9]{6}", content.upper())
    if match is None:
        return "ignored: no order code in content"
    order = db.scalar(
        select(PaymentOrder).where(PaymentOrder.order_code == match.group())
    )
    if order is None:
        return f"ignored: unknown order {match.group()}"
    if order.status != "pending":
        return f"ignored: order {order.order_code} already {order.status}"
    if amount != order.amount_vnd:
        return (
            f"ignored: amount mismatch for {order.order_code} "
            f"({amount} != {order.amount_vnd})"
        )
    txn = (
        payload.get("transactionNumber")
        or payload.get("code")
        or payload.get("referenceCode")
    )
    order.sepay_transaction_id = str(txn) if txn else None
    order.status = "paid"
    order.paid_at = datetime.now(UTC)
    user = db.get(User, order.user_id)
    assert user is not None  # FK ondelete=CASCADE — order exists → user exists
    _apply_plan_to_user(user, order)
    try:
        db.commit()
    except IntegrityError:
        # This transaction already paid for another order (replay / two
        # transfers with the same code) — rollback and keep the truly unpaid
        # order pending.
        db.rollback()
        return f"ignored: duplicate transaction {txn}"
    logger.info(
        "Order %s paid — plan %s until %s (txn %s)",
        order.order_code,
        user.plan_code,
        user.plan_expires_at,
        txn,
    )
    return f"paid: {order.order_code} plan {user.plan_code} active"
