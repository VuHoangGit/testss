"""Tests for the subscription flow + SePay payments: plans, orders, webhook, quotas."""

import os
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.services import credit_service


def _auth_headers(make_token) -> dict[str, str]:
    return {"Authorization": f"Bearer {make_token()}"}


@contextmanager
def _env(**values: str) -> Iterator[None]:
    """Tạm đổi biến môi trường (ưu tiên hơn file .env) rồi khôi phục."""
    from app.core.config import get_settings

    previous = {key: os.environ.get(key) for key in values}
    try:
        os.environ.update(values)
        get_settings.cache_clear()
        yield
    finally:
        for key, old in previous.items():
            if old is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old
        get_settings.cache_clear()


def _set_secret(value: str):
    os.environ["SEPAY_WEBHOOK_SECRET"] = value
    from app.core.config import get_settings

    get_settings.cache_clear()


def _clear_secret():
    os.environ.pop("SEPAY_WEBHOOK_SECRET", None)
    from app.core.config import get_settings

    get_settings.cache_clear()


def test_sepay_webhook_requires_secret(client: TestClient) -> None:
    _set_secret("test-webhook-secret")
    try:
        response = client.post(
            "/api/v1/payments/sepay/webhook",
            json={"id": 123, "transferAmount": 10000},
            headers={"X-Webhook-Secret": "test-webhook-secret"},
        )
        assert response.status_code == 202
        assert response.json()["status"] == "received"
    finally:
        _clear_secret()


def test_sepay_webhook_rejects_invalid_secret(client: TestClient) -> None:
    _set_secret("test-webhook-secret")
    try:
        response = client.post(
            "/api/v1/payments/sepay/webhook",
            json={"id": 123},
            headers={"X-Webhook-Secret": "wrong"},
        )
        assert response.status_code == 401
    finally:
        _clear_secret()


def test_pricing_returns_four_plans(client: TestClient, make_token) -> None:
    """GET /pricing returns the 4 subscription plans from the source table."""
    response = client.get("/api/v1/payments/pricing", headers=_auth_headers(make_token))
    assert response.status_code == 200
    packages = response.json()
    by_code = {p["code"]: p for p in packages}
    assert set(by_code) == {"FREE", "PLUS", "PRO", "MAX"}
    assert by_code["FREE"]["price_vnd"] == 0
    assert by_code["FREE"]["credits"] == 300
    assert by_code["FREE"]["unlimited"] is False
    assert by_code["PLUS"]["price_vnd"] == 50_000
    assert by_code["PLUS"]["credits"] == 1_000
    assert by_code["PRO"]["price_vnd"] == 100_000
    assert by_code["PRO"]["credits"] == 2_500
    assert by_code["PRO"]["badge"] == "Most popular"
    assert by_code["MAX"]["price_vnd"] == 300_000
    assert by_code["MAX"]["credits"] == 10_000
    assert by_code["MAX"]["unlimited"] is True
    # Đúng 4 gói theo thứ tự hiển thị ở màn giá
    assert len(packages) == 4
    assert [p["code"] for p in packages] == ["FREE", "PLUS", "PRO", "MAX"]


def test_create_order_for_plus_plan(client: TestClient, make_token) -> None:
    """Gói Plus 50.000₫: tạo đơn đúng số tiền + gắn plan_code PLUS."""
    order = _create_order(client, make_token, code="PLUS")
    assert order["amount_vnd"] == 50_000
    assert order["credits"] == 1_000
    assert order["plan_code"] == "PLUS"
    assert order["status"] == "pending"
    assert order["transfer_content"] == f"SUBSCRIBE {order['order_code']}"


def test_create_order_rejects_free_and_legacy(client: TestClient, make_token) -> None:
    """FREE is not purchasable; legacy P… packages are deactivated → 404."""
    for code in ("FREE", "P550", "P10000"):
        response = client.post(
            "/api/v1/payments/orders",
            json={"code": code},
            headers=_auth_headers(make_token),
        )
        assert response.status_code == 404, code


def test_webhook_paid_plus_upgrades_plan(client: TestClient, make_token) -> None:
    """Webhook xác nhận Plus → user lên plan + hạn +30 ngày + quota mới."""
    _set_secret("test-webhook-secret")
    try:
        order = _create_order(client, make_token, code="PLUS")
        before = datetime.now(UTC)
        result = _pay_order_via_webhook(client, order, txn="FT26001.0100")
        assert "paid" in result["result"]

        credits = client.get(
            "/api/v1/payments/credits", headers=_auth_headers(make_token)
        ).json()
        assert credits["plan_code"] == "PLUS"
        assert credits["free"] == 1_000
        assert credits["monthly_free"] == 1_000
        expires = datetime.fromisoformat(credits["plan_expires_at"])
        assert expires > before + timedelta(days=29)
    finally:
        _clear_secret()


def test_webhook_early_renewal_stacks_days(client: TestClient, make_token) -> None:
    """Early renewal while active stacks +30 days — no leftover days lost."""
    _set_secret("test-webhook-secret")
    try:
        headers = _auth_headers(make_token)
        order = _create_order(client, make_token, code="PLUS")
        _pay_order_via_webhook(client, order, txn="FT26001.0110")
        first = client.get("/api/v1/payments/credits", headers=headers).json()
        first_expiry = datetime.fromisoformat(first["plan_expires_at"])

        # Renew immediately while ~30 days still remain
        renewal = _create_order(client, make_token, code="PLUS")
        _pay_order_via_webhook(client, renewal, txn="FT26001.0111")
        second = client.get("/api/v1/payments/credits", headers=headers).json()
        second_expiry = datetime.fromisoformat(second["plan_expires_at"])
        # Cộng dồn đúng ~30 ngày kể từ hạn cũ (chống trừ hao theo giây)
        assert second_expiry > first_expiry + timedelta(days=29, hours=23)
        assert credits_plan(second) == "PLUS"
    finally:
        _clear_secret()


def credits_plan(payload: dict) -> str:
    return payload["plan_code"]


def test_expired_plan_degrades_to_free(
    client: TestClient, make_token, db_session_factory
) -> None:
    """Expired plan degrades to FREE quota; monthly refresh returns the FREE quota."""
    headers = _auth_headers(make_token)
    _set_secret("test-webhook-secret")
    try:
        order = _create_order(client, make_token, code="PLUS")
        _pay_order_via_webhook(client, order, txn="FT26001.0120")
    finally:
        _clear_secret()

    with db_session_factory() as db:
        user = _first_user(db)
        user.plan_expires_at = datetime.now(UTC) - timedelta(days=1)
        db.commit()

    credits = client.get("/api/v1/payments/credits", headers=headers).json()
    assert credits["plan_code"] == "FREE"
    assert credits["monthly_free"] == 300
    assert credits["free"] == 1_000  # balance this period stays; only the shown quota changes


def test_max_unlimited_fair_use_blocked(
    client: TestClient, make_token, db_session_factory, monkeypatch
) -> None:
    """MAX unlimited: crossing the 10,000 monthly credit ceiling gets blocked."""
    headers = _auth_headers(make_token)
    _set_secret("test-webhook-secret")
    try:
        order = _create_order(client, make_token, code="MAX")
        _pay_order_via_webhook(client, order, txn="FT26001.0130")
    finally:
        _clear_secret()

    from app.models.user import User

    with db_session_factory() as db:
        user = db.query(User).filter(User.email == "user1@example.com").one()
        # Giả lập đã dùng gần hết trần fair-use (chỉ còn đủ < 1 lượt AI)
        user.credit_free = credit_service.plan_quota("MAX") - 9_980
        db.commit()
        credit_service._hourly_calls.clear()

        monkeypatch.setattr(
            "app.services.ai_service.translate_selection", lambda *a, **k: "Xin chào"
        )
        response = client.post(
            "/api/v1/ai/translate",
            json={"text": "hello", "target_language": "vi"},
            headers=headers,
        )
        assert response.status_code == 402
        assert "Fair-use" in response.json()["detail"]


def test_max_unlimited_hourly_throttle(
    client: TestClient, make_token, db_session_factory, monkeypatch
) -> None:
    """MAX unlimited: over 20 AI calls/hour gets blocked even with credits left."""
    headers = _auth_headers(make_token)
    _set_secret("test-webhook-secret")
    try:
        order = _create_order(client, make_token, code="MAX")
        _pay_order_via_webhook(client, order, txn="FT26001.0140")
    finally:
        _clear_secret()

    credit_service._hourly_calls.clear()
    # Nhồi 20 lượt đã dùng trong giờ này rồi gọi lượt 21
    now = datetime.now(UTC)
    credit_service._hourly_calls["x"] = []
    from app.models.user import User

    with db_session_factory() as db:
        user = db.query(User).filter(User.email == "user1@example.com").one()
    events = [(now, 0)] * 20
    credit_service._hourly_calls[str(user.id)] = list(events)
    monkeypatch.setattr(
        "app.services.ai_service.translate_selection", lambda *a, **k: "Xin chào"
    )
    response = client.post(
        "/api/v1/ai/translate",
        json={"text": "hello", "target_language": "vi"},
        headers=headers,
    )
    credit_service._hourly_calls.clear()
    assert response.status_code == 402
    assert "per hour" in response.json()["detail"]


def test_sepay_webhook_accepts_apikey_scheme(client: TestClient, make_token) -> None:
    """SePay gửi `Authorization: Apikey <key>` khi webhook chọn "API Key"."""
    _set_secret("test-webhook-secret")
    try:
        order = _create_order(client, make_token, code="PLUS")
        response = client.post(
            "/api/v1/payments/sepay/webhook",
            json={
                "content": f"QR {order['transfer_content']} abc",
                "transferAmount": order["amount_vnd"],
                "transferType": "in",
                "transactionNumber": "FT-APIKEY-1",
            },
            # Đúng định dạng SePay thật: scheme "Apikey", không phải "Bearer"
            headers={"Authorization": "Apikey test-webhook-secret"},
        )
        assert response.status_code == 202, response.text
        assert "paid" in response.json()["result"]
        credits = client.get(
            "/api/v1/payments/credits", headers=_auth_headers(make_token)
        ).json()
        assert credits["plan_code"] == "PLUS"
    finally:
        _clear_secret()


def test_new_user_gets_free_plan_quota(client: TestClient, make_token) -> None:
    response = client.get("/api/v1/payments/credits", headers=_auth_headers(make_token))
    assert response.status_code == 200
    data = response.json()
    assert data["plan_code"] == "FREE"
    assert data["free"] == 300
    assert data["purchased"] == 0
    assert data["total"] == 300
    assert data["monthly_free"] == 300
    assert data["ai_cost"] == 50
    assert data["unlimited"] is False
    assert data["plan_expires_at"] is None


def _first_user(db):
    from app.models.user import User

    return db.query(User).filter(User.email == "user1@example.com").one()


def _create_order(client: TestClient, make_token, code: str = "PLUS") -> dict:
    response = client.post(
        "/api/v1/payments/orders",
        json={"code": code},
        headers=_auth_headers(make_token),
    )
    assert response.status_code == 201, response.text
    return response.json()


def _pay_order_via_webhook(client: TestClient, order: dict, txn: str) -> dict:
    response = client.post(
        "/api/v1/payments/sepay/webhook",
        json={
            "id": 1,
            "content": f"chuyen tien {order['transfer_content']} nho giup",
            "transferAmount": order["amount_vnd"],
            "transactionNumber": txn,
            "transferType": "in",
        },
        headers={"X-Webhook-Secret": "test-webhook-secret"},
    )
    assert response.status_code == 202, response.text
    return response.json()


def test_webhook_paid_order_activates_plan(
    client: TestClient, make_token
) -> None:
    _set_secret("test-webhook-secret")
    try:
        order = _create_order(client, make_token)
        assert order["status"] == "pending"
        assert order["order_code"].startswith("DV")
        assert order["transfer_content"] == f"SUBSCRIBE {order['order_code']}"

        result = _pay_order_via_webhook(client, order, txn="FT26001.0001")
        assert "paid" in result["result"]

        # Đơn chuyển paid + user lên đúng plan
        status = client.get(
            f"/api/v1/payments/orders/{order['id']}", headers=_auth_headers(make_token)
        )
        assert status.json()["status"] == "paid"
        credits = client.get(
            "/api/v1/payments/credits", headers=_auth_headers(make_token)
        ).json()
        assert credits["plan_code"] == "PLUS"
    finally:
        _clear_secret()


def test_webhook_duplicate_does_not_double_days(
    client: TestClient, make_token
) -> None:
    _set_secret("test-webhook-secret")
    try:
        order = _create_order(client, make_token)
        _pay_order_via_webhook(client, order, txn="FT26001.0002")
        first = client.get(
            "/api/v1/payments/credits", headers=_auth_headers(make_token)
        ).json()
        first_expiry = datetime.fromisoformat(first["plan_expires_at"])
        # SePay replaying the same transaction must not add days again
        _pay_order_via_webhook(client, order, txn="FT26001.0002")
        second = client.get(
            "/api/v1/payments/credits", headers=_auth_headers(make_token)
        ).json()
        assert datetime.fromisoformat(second["plan_expires_at"]) == first_expiry
    finally:
        _clear_secret()


def test_webhook_wrong_amount_ignored(client: TestClient, make_token) -> None:
    _set_secret("test-webhook-secret")
    try:
        order = _create_order(client, make_token)
        response = client.post(
            "/api/v1/payments/sepay/webhook",
            json={
                "content": order["transfer_content"],
                "transferAmount": order["amount_vnd"] - 1_000,
                "transactionNumber": "FT26001.0003",
            },
            headers={"X-Webhook-Secret": "test-webhook-secret"},
        )
        assert response.status_code == 202
        assert "mismatch" in response.json()["result"]
        status = client.get(
            f"/api/v1/payments/orders/{order['id']}", headers=_auth_headers(make_token)
        )
        assert status.json()["status"] == "pending"
    finally:
        _clear_secret()


def test_payment_history_lists_orders(client: TestClient, make_token) -> None:
    _create_order(client, make_token, code="PLUS")
    _create_order(client, make_token, code="MAX")
    response = client.get("/api/v1/payments/orders", headers=_auth_headers(make_token))
    assert response.status_code == 200
    orders = response.json()
    assert len(orders) == 2
    codes = {o["order_code"][:2] for o in orders}
    assert codes == {"DV"}
    assert {o["plan_code"] for o in orders} == {"PLUS", "MAX"}


def test_order_of_other_user_hidden(client: TestClient, make_token) -> None:
    order = _create_order(client, make_token)
    # A different token sub → different user → cannot see the other's orders
    other = {"Authorization": f"Bearer {make_token(sub='sub-2', email='u2@example.com')}"}
    response = client.get(f"/api/v1/payments/orders/{order['id']}", headers=other)
    assert response.status_code == 404


def test_legacy_order_still_adds_purchased_credits(
    client: TestClient, make_token, db_session_factory
) -> None:
    """Legacy credit order (empty plan_code) still adds credit_purchased."""
    _set_secret("test-webhook-secret")
    try:
        order = _create_order(client, make_token, code="PLUS")
        from app.models.payment import PaymentOrder

        with db_session_factory() as db:
            row = db.get(PaymentOrder, uuid.UUID(order["id"]))
            row.plan_code = ""  # simulate an order created before the migration
            db.commit()

        _pay_order_via_webhook(client, order, txn="FT26001.0150")
        credits = client.get(
            "/api/v1/payments/credits", headers=_auth_headers(make_token)
        ).json()
        assert credits["plan_code"] == "FREE"
        assert credits["purchased"] == order["credits"]
    finally:
        _clear_secret()


def test_ai_translate_charges_and_refunds(
    client: TestClient, make_token, monkeypatch
) -> None:
    headers = _auth_headers(make_token)

    # Successful call: charges exactly 50
    monkeypatch.setattr(
        "app.services.ai_service.translate_selection", lambda *a, **k: "Xin chào"
    )
    response = client.post(
        "/api/v1/ai/translate",
        json={"text": "hello", "target_language": "vi"},
        headers=headers,
    )
    assert response.status_code == 200
    credits = client.get("/api/v1/payments/credits", headers=headers).json()
    assert credits["total"] == 250

    # Failed AI call: refunds 50, balance unchanged
    def _boom(*args, **kwargs):
        from app.services.ai_service import AIServiceError

        raise AIServiceError("AI quá tải")

    monkeypatch.setattr("app.services.ai_service.translate_selection", _boom)
    response = client.post(
        "/api/v1/ai/translate",
        json={"text": "hello", "target_language": "vi"},
        headers=headers,
    )
    assert response.status_code == 503
    credits = client.get("/api/v1/payments/credits", headers=headers).json()
    assert credits["total"] == 250


def test_ai_blocked_when_out_of_credits(
    client: TestClient, make_token, db_session_factory
) -> None:
    headers = _auth_headers(make_token)
    # Create the user first (first call), then drain credits to 0
    client.get("/api/v1/payments/credits", headers=headers)
    from app.models.user import User

    with db_session_factory() as db:
        user = db.query(User).filter(User.email == "user1@example.com").one()
        user.credit_free = 0
        user.credit_purchased = 0
        db.commit()

    response = client.post(
        "/api/v1/ai/translate",
        json={"text": "hello", "target_language": "vi"},
        headers=headers,
    )
    assert response.status_code == 402
    assert "Not enough credits" in response.json()["detail"]


def test_charge_deducts_free_before_purchased(
    client: TestClient, make_token, db_session_factory
) -> None:
    client.get("/api/v1/payments/credits", headers=_auth_headers(make_token))
    from app.models.user import User

    with db_session_factory() as db:
        user = db.query(User).filter(User.email == "user1@example.com").one()
        user.credit_free = 30
        user.credit_purchased = 100
        db.commit()
        credit_service.charge(db, user)
        # Monthly quota is spent first (30→0), purchased credits cover the rest (100→80)
        assert user.credit_free == 0
        assert user.credit_purchased == 80


def test_order_qr_url_is_png_ready(client: TestClient, make_token) -> None:
    """QR phải trỏ dịch vụ trả PNG — Flutter `Image.network` không vẽ được SVG."""
    with _env(SEPAY_BANK_ACCOUNT="0123456789", SEPAY_BANK_BIN="MB"):
        order = _create_order(client, make_token)
        url = order["qr_url"]
        assert url is not None
        assert url.startswith("https://qr.sepay.vn/img?")
        assert "acc=0123456789" in url
        assert "bank=MB" in url
        assert f"amount={order['amount_vnd']}" in url
        # Nội dung chuyển khoản nằm trong `des` để SePay đối chiếu được
        assert f"des=SUBSCRIBE+{order['order_code']}" in url
        # Thông tin chuyển khoản hiển thị cạnh QR
        assert order["bank_account"] == "0123456789"
        assert order["bank_bin"] == "MB"


def test_order_without_bank_account_has_no_qr(client: TestClient, make_token) -> None:
    """Chưa cấu hình số TK → không có QR, đơn vẫn tạo được bình thường."""
    with _env(SEPAY_BANK_ACCOUNT="", SEPAY_ACCOUNT_NAME=""):
        order = _create_order(client, make_token)
        assert order["qr_url"] is None
        assert order["bank_account"] == ""


def test_old_order_gets_fresh_qr_url(
    client: TestClient, make_token, db_session_factory
) -> None:
    """Đơn cũ lưu URL hỏng vẫn trả QR đúng — QR tính lúc đọc, không dùng cột."""
    with _env(SEPAY_BANK_ACCOUNT="0123456789", SEPAY_BANK_BIN="MB"):
        order = _create_order(client, make_token)

        # Giả lập đơn tạo từ code cũ: URL 404 đã lưu cứng trong DB
        from app.models.payment import PaymentOrder

        with db_session_factory() as db:
            row = db.get(PaymentOrder, uuid.UUID(order["id"]))
            row.qr_url = "https://img.vietqr.io/Image/QR?AccountNo=1&Bank=MB"
            db.commit()

        fetched = client.get(
            f"/api/v1/payments/orders/{order['id']}", headers=_auth_headers(make_token)
        ).json()
        assert fetched["qr_url"].startswith("https://qr.sepay.vn/img?")
        assert "acc=0123456789" in fetched["qr_url"]


def test_webhook_ignores_money_out(client: TestClient, make_token) -> None:
    """An OUTGOING transfer containing an order code must not activate a plan."""
    _set_secret("test-webhook-secret")
    try:
        order = _create_order(client, make_token)
        response = client.post(
            "/api/v1/payments/sepay/webhook",
            json={
                "content": order["transfer_content"],
                "transferAmount": order["amount_vnd"],
                "transactionNumber": "FT26001.0009",
                "transferType": "out",
            },
            headers={"X-Webhook-Secret": "test-webhook-secret"},
        )
        assert response.status_code == 202
        assert "transferType=out" in response.json()["result"]
        status = client.get(
            f"/api/v1/payments/orders/{order['id']}", headers=_auth_headers(make_token)
        )
        assert status.json()["status"] == "pending"
    finally:
        _clear_secret()
