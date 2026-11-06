"""Quản lý credit AI cho user: reset monthly free, trừ/hoàn credit mỗi lượt gọi.

Quy tắc: mỗi tháng cấp `credit_monthly_free` (300) vào phần free — reset lazy
khi đọc/ghi (so kỳ "YYYY-MM"), không cần cron. Credit nạp mua cộng dồn, không
bị reset. Trừ free trước, hết free mới trừ credit mua.
"""

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.user import User


class InsufficientCredits(Exception):
    """Không đủ credit để gọi tính năng AI — UI hướng dẫn nạp thêm."""

    def __init__(self, message: str, balance: int, cost: int):
        super().__init__(message)
        self.message = message
        self.balance = balance
        self.cost = cost


def _current_period() -> str:
    return datetime.now(UTC).strftime("%Y-%m")


def ensure_monthly_refresh(db: Session, user: User) -> User:
    """Reset 300 credit free nếu sang kỳ tháng mới (idempotent)."""
    period = _current_period()
    if user.credit_period == period:
        return user
    user.credit_free = get_settings().credit_monthly_free
    user.credit_period = period
    db.commit()
    return user


def balance_of(db: Session, user: User) -> int:
    ensure_monthly_refresh(db, user)
    return user.credit_free + user.credit_purchased


def charge(db: Session, user: User, cost: int | None = None) -> int:
    """Trừ credit cho 1 lượt gọi AI; trả về số dư sau khi trừ.

    Ném [InsufficientCredits] khi không đủ — endpoint map thành HTTP 402.
    """
    settings = get_settings()
    cost = settings.credit_cost_ai if cost is None else cost
    ensure_monthly_refresh(db, user)
    if user.credit_free + user.credit_purchased < cost:
        raise InsufficientCredits(
            f"Not enough credits (need {cost}, you have "
            f"{user.credit_free + user.credit_purchased}). Top up credits "
            "under Account → Buy credits.",
            balance=user.credit_free + user.credit_purchased,
            cost=cost,
        )
    # Trừ free trước, thiếu bao nhiêu lấy tiếp từ credit đã mua
    take_from_purchased = max(0, cost - user.credit_free)
    user.credit_free = max(0, user.credit_free - cost)
    user.credit_purchased -= take_from_purchased
    db.commit()
    return user.credit_free + user.credit_purchased


def refund(db: Session, user: User, amount: int | None = None) -> None:
    """Hoàn credit khi lượt gọi AI lỗi (trả về phần free trước)."""
    amount = get_settings().credit_cost_ai if amount is None else amount
    # Hoàn vào free nhưng không vượt mức free của kỳ hiện tại
    monthly_free = get_settings().credit_monthly_free
    to_free = min(amount, monthly_free - user.credit_free)
    user.credit_free += to_free
    user.credit_purchased += amount - to_free
    db.commit()
