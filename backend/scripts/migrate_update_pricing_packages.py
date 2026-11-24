"""Thêm cột `badge` + chuyển dữ liệu sang thang gói nạp mới (chạy 1 lần).

Gói mới: P200 (20k→200), P550 (50k→550), P1250 (100k→1.250), P3000 (200k→3.000).
DB dev/prod đang có dữ liệu thật nên KHÔNG drop/recreate. `ensure_pricing_seed`
chỉ INSERT gói thiếu + sửa name, KHÔNG đè price/credits gói cũ → script này
UPDATE thẳng theo code. Đơn PaymentOrder cũ tham chiếu `package_id` (không phải
code) nên đổi code/giá gói KHÔNG làm hỏng đơn cũ.

Thứ tự UPDATE tránh đụng unique constraint `code`: đổi code xa nhất trước
(P10000→P3000, P2500→P1250, P1000→P550), P50 (đã bị thay bởi P200) bị xóa
cuối cùng. Idempotent — chạy lại không lỗi, không đổi gì thêm.

Chạy:  python scripts/migrate_update_pricing_packages.py
"""

import sys
from pathlib import Path

# Console Windows mặc định cp1252 — không in được chữ có dấu, stdout chuyển UTF-8
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import inspect, text  # noqa: E402

from app.db.session import SessionLocal, engine  # noqa: E402

# Thang giá mới: code cũ → (code mới, tên, giá, credit, badge).
# Thứ tự dict là thứ tự UPDATE — không được đổi bừa nếu không suy nghĩ lại
# unique constraint trên cột code.
_PACKAGE_UPDATES: dict[str, tuple[str, str, int, int, str | None]] = {
    "P10000": ("P3000", "Cao cấp — 3.000 credit", 200_000, 3_000, None),
    "P2500": ("P1250", "Giá trị — 1.250 credit", 100_000, 1_250, "Tiết kiệm nhất"),
    "P1000": ("P550", "Tiêu chuẩn — 550 credit", 50_000, 550, "Phổ biến nhất"),
    # P50 không có dòng ánh xạ — bị xóa (thay bởi P200)
}


def main() -> int:
    # (a) Thêm cột badge nếu còn thiếu (bỏ qua nếu đã có)
    existing_cols = {col["name"] for col in inspect(engine).get_columns("pricing_packages")}
    if "badge" not in existing_cols:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE pricing_packages ADD COLUMN badge VARCHAR(40) NULL"))
        print("Da them cot pricing_packages.badge")
    else:
        print("Cot badge da ton tai — bo qua ALTER TABLE")

    # (b) Chuyển dữ liệu gói cũ sang thang giá mới (idempotent theo code đích)
    from app.services import payment_service

    with engine.connect() as conn:
        rows = {
            code: (name, price, credits)
            for code, name, price, credits in conn.execute(
                text("SELECT code, name, price_vnd, credits FROM pricing_packages")
            )
        }

    # P50 đã bị thay bởi P200: xóa trước để code "P200" được insert ở bước seed
    if "P50" in rows:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM pricing_packages WHERE code = 'P50'"))
        print("Da xoa goi P50 (thay boi P200)")

    # sort_order của gói mới = vị trí trong DEFAULT_PACKAGES (thứ tự hiển thị UI)
    sort_index = {str(p["code"]): i for i, p in enumerate(payment_service.DEFAULT_PACKAGES)}

    with engine.begin() as conn:
        for old_code, (new_code, name, price, credits, badge) in _PACKAGE_UPDATES.items():
            if old_code not in rows:
                print(f"Bo qua {old_code} (khong ton tai — da migrate roi)")
                continue
            conn.execute(
                text(
                    "UPDATE pricing_packages SET code = :code, name = :name, "
                    "price_vnd = :price, credits = :credits, badge = :badge, "
                    "sort_order = :sort WHERE code = :old"
                ),
                {
                    "code": new_code,
                    "name": name,
                    "price": price,
                    "credits": credits,
                    "badge": badge,
                    "sort": sort_index[new_code],
                    "old": old_code,
                },
            )
            print(f"Da cap nhat {old_code} -> {new_code} ({name})")

    # Đảm bảo đủ 4 gói mới (insert gói thiếu, vd P200; sửa name nếu lệch)
    with SessionLocal() as db:
        payment_service.ensure_pricing_seed(db)
    print("Seed goi theo thang gia moi: xong (idempotent)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
