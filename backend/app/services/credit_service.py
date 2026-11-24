"""AI credit management per user: plan quotas, charge/refund per AI call.

Subscription model: each user has a `plan_code` (FREE/PLUS/PRO/MAX) valid until
`plan_expires_at`. The monthly quota equals the quota of the EFFECTIVE plan
(expired plans degrade to FREE). Quotas reset lazily per "YYYY-MM" period on
read/write — no cron needed. Legacy prepaid credits (`credit_purchased`) are
kept as-is: never expire, spent only after the monthly quota runs out.

MAX plan (unlimited): skips the insufficient-credit check but still enforces
fair-use guards — a monthly credit ceiling plus AI calls per hour (tracked in
process memory).
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.user import User

# AI calls made within the last hour per MAX user: user_id → list of
# (timestamp, 0) markers. Process-memory only — a restart clears it, which is
# acceptable for an abuse-prevention layer (not billing).
_hourly_calls: dict[str, list[tuple[datetime, int]]] = {}


class InsufficientCredits(Exception):
    """Not enough credits for an AI feature — UI guides the user to upgrade."""

    def __init__(self, message: str, balance: int, cost: int):
        super().__init__(message)
        self.message = message
        self.balance = balance
        self.cost = cost


def effective_plan(user: User) -> str:
    """Effective plan: plan_code while still valid, otherwise FREE."""
    if user.plan_code == "FREE" or user.plan_expires_at is None:
        return "FREE"
    expires = user.plan_expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=UTC)
    return user.plan_code if expires > datetime.now(UTC) else "FREE"


def plan_quota(plan_code: str) -> int:
    """Monthly credit quota of a plan (settings-driven, no deploy needed)."""
    settings = get_settings()
    return {
        "FREE": settings.plan_quota_free,
        "PLUS": settings.plan_quota_plus,
        "PRO": settings.plan_quota_pro,
        "MAX": settings.plan_quota_max,
    }.get(plan_code.upper(), settings.plan_quota_free)


def _current_period() -> str:
    return datetime.now(UTC).strftime("%Y-%m")


def ensure_monthly_refresh(db: Session, user: User) -> User:
    """Reset the monthly quota when a new period starts (idempotent).

    The new quota is the quota of the EFFECTIVE plan at reset time — a user
    whose Plus plan expired mid-month only gets the FREE quota next period.
    """
    period = _current_period()
    if user.credit_period == period:
        return user
    user.credit_free = plan_quota(effective_plan(user))
    user.credit_period = period
    db.commit()
    return user


def _check_hourly_rate(user: User) -> None:
    """MAX fair-use: at most N AI calls per rolling 1-hour window."""
    settings = get_settings()
    limit = settings.unlimited_hourly_calls
    if limit <= 0:
        return
    now = datetime.now(UTC)
    events = [e for e in _hourly_calls.get(str(user.id), []) if now - e[0] < timedelta(hours=1)]
    if len(events) >= limit:
        raise InsufficientCredits(
            f"Fair-use limit: max {limit} AI calls per hour on the Max plan. "
            "Please try again later.",
            balance=user.credit_free + user.credit_purchased,
            cost=0,
        )
    events.append((now, 0))
    _hourly_calls[str(user.id)] = events


def _check_monthly_ceiling(user: User) -> None:
    """MAX fair-use: block once monthly usage crosses the credit ceiling."""
    settings = get_settings()
    ceiling = settings.max_unlimited_monthly_credits
    if ceiling <= 0:
        return
    quota = plan_quota("MAX")
    used = quota - user.credit_free
    if used + settings.credit_cost_ai > ceiling:
        raise InsufficientCredits(
            f"Fair-use limit: the Max plan includes up to {ceiling} credits "
            "per month. Your usage reached this ceiling — it resets next month.",
            balance=user.credit_free + user.credit_purchased,
            cost=settings.credit_cost_ai,
        )


def charge(db: Session, user: User, cost: int | None = None) -> int:
    """Charge credits for one AI call; returns the balance afterwards.

    Raises [InsufficientCredits] when short — endpoints map it to HTTP 402.
    MAX unlimited plan: no insufficient-credit check, but fair-use guards
    (calls/hour + monthly credit ceiling) still apply and usage is still
    tracked by decrementing credit_free.
    """
    settings = get_settings()
    cost = settings.credit_cost_ai if cost is None else cost
    ensure_monthly_refresh(db, user)
    is_unlimited = effective_plan(user) == "MAX"
    if is_unlimited:
        _check_hourly_rate(user)
        _check_monthly_ceiling(user)
    elif user.credit_free + user.credit_purchased < cost:
        raise InsufficientCredits(
            f"Not enough credits (need {cost}, you have "
            f"{user.credit_free + user.credit_purchased}). Upgrade your plan "
            "under Account → Plans.",
            balance=user.credit_free + user.credit_purchased,
            cost=cost,
        )
    # Spend the monthly quota first; the remainder comes from purchased credits
    take_from_purchased = max(0, cost - user.credit_free)
    user.credit_free = max(0, user.credit_free - cost)
    user.credit_purchased -= take_from_purchased
    db.commit()
    return user.credit_free + user.credit_purchased


def refund(db: Session, user: User, amount: int | None = None) -> None:
    """Refund credits when an AI call fails (monthly quota first)."""
    amount = get_settings().credit_cost_ai if amount is None else amount
    # Refund into the monthly quota but never above the current plan's quota
    quota = plan_quota(effective_plan(user))
    to_free = min(amount, quota - user.credit_free)
    user.credit_free += to_free
    user.credit_purchased += amount - to_free
    db.commit()

