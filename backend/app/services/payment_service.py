"""Tạo đơn nạp credit + đối chiếu webhook SePay (idempotent, chống trùng)."""

import logging
import re
import secrets
from datetime import UTC, datetime
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

# Gói nạp mặc định — seed idempotent theo code, chạy ở startup và migration.
# Thứ tự trong list là `sort_order` (hiện từ trên xuống ở màn Mua credit).
DEFAULT_PACKAGES: list[dict[str, object]] = [
    # Gói nhỏ nhất: đủ cho 1 lượt gọi AI (50 credit), tiện nạp thử/chuyển khoản thật
    {"code": "P50", "name": "50-credit pack", "price_vnd": 10_000, "credits": 50},
    {"code": "P1000", "name": "1,000-credit pack", "price_vnd": 100_000, "credits": 1_000},
    {"code": "P2500", "name": "2,500-credit pack", "price_vnd": 200_000, "credits": 2_500},
    {"code": "P10000", "name": "10,000-credit pack", "price_vnd": 500_000, "credits": 10_000},
]


def ensure_pricing_seed(db: Session) -> None:
    """Chèn các gói mặc định nếu bảng còn trống (idempotent theo code).

    Gói đã có nhưng tên khác (vd DB tạo trước khi đổi sang tên tiếng Anh) được
    cập nhật lại tên hiển thị; giá/credit giữ nguyên để không đổi dữ liệu bán.
    """
    for i, pkg in enumerate(DEFAULT_PACKAGES):
        exists = db.scalar(select(PricingPackage).where(PricingPackage.code == pkg["code"]))
        if exists is None:
            db.add(
                PricingPackage(
                    code=str(pkg["code"]),
                    name=str(pkg["name"]),
                    price_vnd=int(pkg["price_vnd"]),  # type: ignore[arg-type]
                    credits=int(pkg["credits"]),  # type: ignore[arg-type]
                    sort_order=i,
                )
            )
        elif exists.name != str(pkg["name"]):
            exists.name = str(pkg["name"])
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
    """Sinh mã đơn "DV" + 6 ký tự duy nhất (thử lại nếu trùng hiếm gặp)."""
    for _ in range(10):
        code = "DV" + "".join(secrets.choice(_CODE_ALPHABET) for _ in range(6))
        taken = db.scalar(select(PaymentOrder).where(PaymentOrder.order_code == code))
        if taken is None:
            return code
    raise RuntimeError("Could not generate a unique order code")


# Dịch vụ ảnh QR của chính SePay — trả PNG (img.vietqr.io chỉ trả SVG, Flutter
# `Image.network` không vẽ được SVG nên không dùng được).
QR_IMAGE_BASE_URL = "https://qr.sepay.vn/img"


def build_qr_url(amount_vnd: int, transfer_content: str) -> str | None:
    """URL ảnh QR chuyển khoản (PNG) nếu đã cấu hình số tài khoản nhận.

    Trả None khi chưa cấu hình `SEPAY_BANK_ACCOUNT` — UI khi đó chỉ hiện
    thông tin chuyển khoản dạng chữ.
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
    package = get_package(db, package_code)
    if package is None or not package.active:
        raise PackageNotFoundError(f"Package not found: {package_code}")
    code = _new_order_code(db)
    content = f"TOPUP {code}"
    order = PaymentOrder(
        user_id=user.id,
        package_id=package.id,
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
    """Mã gói không tồn tại hoặc đã tắt."""


def process_sepay_webhook(db: Session, payload: dict) -> str:
    """Đối chiếu giao dịch tiền vào với đơn pending → cộng credit.

    Luôn trả về mô tả kết quả để endpoint log; các trường hợp không khớp
    (không có mã đơn/sai số tiền/đơn đã xử lý) đều an toàn — trả 2xx cho
    SePay, không cộng credit.

    Chống trùng 2 lớp: (1) đơn phải đang pending; (2) UNIQUE
    sepay_transaction_id — SePay replay lại giao dịch cũ sẽ bị IntegrityError.
    """
    content = str(payload.get("content") or "")
    try:
        amount = int(payload.get("transferAmount") or 0)
    except (TypeError, ValueError):
        amount = 0
    # SePay gửi cả tiền ra lẫn tiền vào của tài khoản. Chỉ cộng credit cho
    # giao dịch TIỀN VÀO — nếu không, một lệnh chuyển tiền ra có nội dung
    # chứa mã đơn sẽ bị tính nhầm là đã trả tiền.
    transfer_type = str(payload.get("transferType") or "in").strip().lower()
    if transfer_type != "in":
        return f"ignored: transferType={transfer_type} (not money in)"
    # Đối chiếu tài khoản nhận: nếu đã cấu hình SEPAY_BANK_ACCOUNT và payload có
    # `accountNumber` thì phải khớp — chặn trường hợp secret lộ rồi bị bơm giao
    # dịch giả cho tài khoản khác. Payload không có trường này thì bỏ qua (một số
    # cấu hình webhook của SePay không gửi kèm).
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
    assert user is not None  # FK ondelete=CASCADE — đơn tồn tại thì user tồn tại
    user.credit_purchased += order.credits
    try:
        db.commit()
    except IntegrityError:
        # Giao dịch này đã dùng để trả cho đơn khác (replay/chuyển 2 lần cùng
        # mã) — rollback, giữ đơn pending thật sự chưa được trả tiền.
        db.rollback()
        return f"ignored: duplicate transaction {txn}"
    logger.info("Order %s paid +%d credits (txn %s)", order.order_code, order.credits, txn)
    return f"paid: {order.order_code} +{order.credits} credits"
