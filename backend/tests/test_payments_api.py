"""Test luồng credit + thanh toán SePay: gói, đơn nạp, webhook, trừ credit AI."""

import os
from collections.abc import Iterator
from contextlib import contextmanager

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


def test_pricing_returns_seeded_packages(
    client: TestClient, make_token, db_session_factory
) -> None:
    response = client.get("/api/v1/payments/pricing", headers=_auth_headers(make_token))
    assert response.status_code == 200
    packages = response.json()
    by_code = {p["code"]: p for p in packages}
    assert by_code["P1000"]["price_vnd"] == 100_000
    assert by_code["P1000"]["credits"] == 1_000
    assert by_code["P2500"]["credits"] == 2_500
    assert by_code["P10000"]["price_vnd"] == 500_000


def test_new_user_gets_monthly_free_credits(client: TestClient, make_token) -> None:
    response = client.get("/api/v1/payments/credits", headers=_auth_headers(make_token))
    assert response.status_code == 200
    data = response.json()
    assert data["free"] == 300
    assert data["purchased"] == 0
    assert data["total"] == 300
    assert data["ai_cost"] == 50


def _create_order(client: TestClient, make_token, code: str = "P1000") -> dict:
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


def test_webhook_pays_order_and_adds_credits(
    client: TestClient, make_token, db_session_factory
) -> None:
    _set_secret("test-webhook-secret")
    try:
        order = _create_order(client, make_token)
        assert order["status"] == "pending"
        assert order["order_code"].startswith("DV")
        assert order["transfer_content"] == f"NAP {order['order_code']}"

        result = _pay_order_via_webhook(client, order, txn="FT25001.0001")
        assert "paid" in result["result"]

        # Đơn chuyển paid + user cộng đúng credit gói
        status = client.get(
            f"/api/v1/payments/orders/{order['id']}", headers=_auth_headers(make_token)
        )
        assert status.json()["status"] == "paid"
        credits = client.get(
            "/api/v1/payments/credits", headers=_auth_headers(make_token)
        ).json()
        assert credits["purchased"] == 1_000
    finally:
        _clear_secret()


def test_webhook_duplicate_does_not_double_credit(
    client: TestClient, make_token
) -> None:
    _set_secret("test-webhook-secret")
    try:
        order = _create_order(client, make_token)
        _pay_order_via_webhook(client, order, txn="FT25001.0002")
        # SePay replay cùng giao dịch → không cộng thêm
        _pay_order_via_webhook(client, order, txn="FT25001.0002")
        credits = client.get(
            "/api/v1/payments/credits", headers=_auth_headers(make_token)
        ).json()
        assert credits["purchased"] == 1_000
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
                "transactionNumber": "FT25001.0003",
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
    _create_order(client, make_token, code="P2500")
    _create_order(client, make_token, code="P10000")
    response = client.get("/api/v1/payments/orders", headers=_auth_headers(make_token))
    assert response.status_code == 200
    orders = response.json()
    assert len(orders) == 2
    codes = {o["order_code"][:2] for o in orders}
    assert codes == {"DV"}


def test_order_of_other_user_hidden(client: TestClient, make_token) -> None:
    order = _create_order(client, make_token)
    # Token sub khác → user khác → không thấy đơn của người kia
    other = {"Authorization": f"Bearer {make_token(sub='sub-2', email='u2@example.com')}"}
    response = client.get(f"/api/v1/payments/orders/{order['id']}", headers=other)
    assert response.status_code == 404


def test_ai_translate_charges_and_refunds(
    client: TestClient, make_token, monkeypatch
) -> None:
    headers = _auth_headers(make_token)

    # Lượt thành công: trừ đúng 50
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

    # Lượt AI lỗi: hoàn 50, số dư giữ nguyên
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
    # Tạo user trước (lần gọi đầu), rồi xà credit về 0
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
    assert "Không đủ credit" in response.json()["detail"]


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
        # Free hết trước (30→0), mua bị trừ phần còn thiếu (100→80)
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
        assert f"des=NAP+{order['order_code']}" in url
        # Thông tin chuyển khoản hiển thị cạnh QR
        assert order["bank_account"] == "0123456789"
        assert order["bank_bin"] == "MB"


def test_order_without_bank_account_has_no_qr(client: TestClient, make_token) -> None:
    """Chưa cấu hình số TK → không có QR, đơn vẫn tạo được bình thường."""
    with _env(SEPAY_BANK_ACCOUNT="", SEPAY_ACCOUNT_NAME=""):
        order = _create_order(client, make_token)
        assert order["qr_url"] is None
        assert order["bank_account"] == ""


def test_webhook_ignores_money_out(client: TestClient, make_token) -> None:
    """Giao dịch tiền RA có chứa mã đơn không được cộng credit."""
    _set_secret("test-webhook-secret")
    try:
        order = _create_order(client, make_token)
        response = client.post(
            "/api/v1/payments/sepay/webhook",
            json={
                "content": order["transfer_content"],
                "transferAmount": order["amount_vnd"],
                "transactionNumber": "FT25001.0009",
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
