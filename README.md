# DocuVault — quản lý tài liệu + AI (Flutter + FastAPI)

Ứng dụng đa nền tảng (web/desktop/mobile) kiểu "Google Drive + AI": kho tài liệu,
công cụ PDF, OCR, so sánh hợp đồng, chatbot RAG.

Trạng thái hiện tại — đã hoàn thành:

- **Sprint 1**: hạ tầng, đăng nhập, kho tài liệu, viewer và công cụ PDF.
- **Sprint 2**: OCR / Key-Value / dịch / chatbot RAG, **credit AI** và **nạp credit
  qua SePay** (tạo đơn → QR chuyển khoản → webhook tự cộng credit), màn Mua credit
  và Lịch sử thanh toán.

## Yêu cầu máy

- Python 3.12 (đã có venv sẵn tại `backend/.venv`)
- Flutter SDK (máy này đặt ở `C:\Users\hoang\flutter`)
- Docker Desktop (tùy chọn — chỉ cần khi muốn chạy PostgreSQL thật; demo dùng SQLite)

## Cách chạy (PowerShell)

### 1. Chạy backend

```powershell
cd C:\Users\hoang\Downloads\testss\backend
# Lần đầu: tạo DB (SQLite — không cần Docker, đã trỏ sẵn trong backend/.env)
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

Kiểm tra: mở `http://localhost:8000/health` →
`{"status":"ok","app":"DocuVault API","ai_configured":true}`.

> Muốn dùng PostgreSQL thật: bật Docker Desktop → `docker compose up -d` (ở gốc repo) → sửa `DATABASE_URL` trong `backend/.env` thành `postgresql+psycopg://docuvault:docuvault@localhost:5432/docuvault` → chạy lại `alembic upgrade head`.

### Tài khoản đăng nhập

Đăng nhập (email/mật khẩu và Google) do **Supabase Auth** quản lý phía client —
backend **không có** endpoint đăng nhập, chỉ verify access token qua JWKS.

- Tài khoản tạo trên **Supabase Dashboard → Authentication → Users**, hoặc bấm
  **"Chưa có tài khoản? Đăng ký"** ngay trên màn Login (mật khẩu ≥ 6 ký tự).
- Nếu project bật *Confirm email*, phải xác nhận email trước khi đăng nhập được
  (app có hiện thông báo nhắc việc này).
- `backend` cần `SUPABASE_URL` trỏ đúng project; client cần `SUPABASE_URL` +
  `SUPABASE_ANON_KEY` khi build (mặc định đã có sẵn trong `lib/core/config/app_config.dart`).

### 2. Chạy app Flutter (web — máy này chỉ chạy được Edge)

Mở terminal thứ hai:

```powershell
cd C:\Users\hoang\Downloads\testss
$env:Path = "C:\Users\hoang\flutter\bin;$env:Path"
flutter run -d edge
```

- Đăng nhập bằng tài khoản Supabase ở trên.
- Tab **Tài liệu**: "Tải lên" (chọn file, xem tiến độ), "Thư mục mới", chip thư mục để lọc,
  bấm vào PDF để mở viewer,
  menu ⋮ mỗi file: **Tải xuống / Tách trang / Đặt mật khẩu / Gỡ mật khẩu / Xóa**,
  nút **"Chọn để gộp"**: tích ≥2 PDF → đặt tên → gộp thành file mới (bản gốc giữ nguyên).
- Tab **Tài khoản → Credits**: xem số dư, **Mua credit** (QR SePay) và **Lịch sử thanh toán**.

### 3. Chạy test

```powershell
# Backend
cd C:\Users\hoang\Downloads\testss\backend
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .

# Flutter
cd C:\Users\hoang\Downloads\testss
flutter analyze
flutter test
```

## Cấu trúc

```
backend/                 FastAPI + SQLAlchemy + Alembic
  app/api/v1/            auth, folders, documents, ai, payments
  app/services/          auth, storage (đĩa cục bộ), pdf (pypdf), ai,
                         credit (trừ/hoàn credit), payment (đơn + webhook SePay)
  migrations/            0001 users+sessions, 0002 folders+documents+permissions,
                         0003 password login, 0004 payments+credits
  scripts/               migrate_add_*.py (migration bổ sung, idempotent)
  tests/                 pytest (110 test)
lib/                     Flutter Clean Architecture
  core/                  config, lỗi, Dio + interceptor refresh token, file saver
  domain/                entities + repository interfaces
  data/                  models + repository impl
  presentation/          Riverpod controllers + screens (Login, Shell, Documents,
                         AI, payments: Mua credit + Lịch sử thanh toán)
docs/                    phân tích nghiệp vụ (sprint 1) + luồng voice
```

## Đăng nhập Google

Google login cũng do **Supabase Auth** lo, không cần khai báo client ID ở backend:

1. Supabase Dashboard → **Authentication → Providers → Google** → bật và dán
   *Client ID* / *Client Secret* lấy từ
   [Google Cloud Console](https://console.cloud.google.com) (Credentials → OAuth client ID).
2. Trong Google Cloud, thêm **Authorized redirect URI**:
   `https://<project-ref>.supabase.co/auth/v1/callback`.
3. Client chỉ cần bấm "Continue with Google" — Supabase trả access token, backend
   verify như mọi token khác.

## Biến môi trường backend (`.env` hoặc set thủ công)

| Biến | Ý nghĩa | Mặc định |
|---|---|---|
| `SUPABASE_URL` | URL project Supabase (backend verify token qua JWKS) | **bắt buộc** |
| `DATABASE_URL` | Postgres hoặc `sqlite:///./ten.db` | Postgres local |
| `ALLOWED_EMAIL_DOMAINS` | Chặn domain (rỗng = mở) | rỗng |
| `CORS_ORIGINS` | Origin web được gọi API | rỗng |
| `DOCUMENTS_DIR` | Thư mục lưu file upload | `backend/storage/documents` |
| `MAX_UPLOAD_MB` | Giới hạn 1 file | 50 |
| `ANTHROPIC_AUTH_TOKEN` | Token dịch vụ AI (API tương thích Anthropic), chỉ đặt ở backend | rỗng |
| `ANTHROPIC_BASE_URL` | Base URL dịch vụ AI | `https://api.z.ai/api/anthropic` |
| `ANTHROPIC_MODEL` | Model cho OCR/chat/dịch | `glm-4.6` |
| `ANTHROPIC_TIMEOUT_SECONDS` | Timeout gọi AI | 90 |
| `CREDIT_MONTHLY_FREE` | Credit free cấp mỗi tháng | 300 |
| `CREDIT_COST_AI` | Credit trừ mỗi lượt gọi AI | 50 |
| `SEPAY_WEBHOOK_SECRET` | Secret xác thực webhook SePay | rỗng |
| `SEPAY_BANK_ACCOUNT` | Số TK nhận tiền nạp (để hiện ảnh QR) | rỗng |
| `SEPAY_BANK_BIN` | Mã ngân hàng cho QR (MB, VCB, ICB… hoặc BIN) | `MB` |
| `SEPAY_ACCOUNT_NAME` | Tên chủ tài khoản hiển thị khi nạp | rỗng |

### Credit AI + thanh toán SePay

Mỗi tài khoản được **300 credit free mỗi tháng** (tự reset đầu tháng, không
cần cron — reset lazy khi đọc/ghi). Credit nạp mua **không hết hạn**. Mỗi lượt
gọi tính năng AI (OCR, OCR→Word, dịch, mỗi tin nhắn chat) tốn **50 credit**;
AI lỗi thì tự hoàn. Hết credit → HTTP 402 kèm hướng dẫn nạp.

Gói nạp (bảng `pricing_packages`, seed idempotent): 100.000₫ → 1.000 credit,
200.000₫ → 2.500 credit, 500.000₫ → 10.000 credit.

Luồng thanh toán:

1. App gọi `POST /api/v1/payments/orders` tạo đơn → mã đơn `DVXXXXXX` +
   nội dung chuyển khoản `NAP DVXXXXXX` + URL ảnh QR.
   Ảnh QR lấy từ **`https://qr.sepay.vn/img`** (trả PNG — `img.vietqr.io` chỉ
   trả SVG nên `Image.network` của Flutter không vẽ được). Chưa điền
   `SEPAY_BANK_ACCOUNT` thì `qr_url = null`, app chỉ hiện thông tin dạng chữ.
2. Người dùng chuyển khoản đúng **số tiền** + **nội dung chứa mã đơn**.
3. SePay gọi webhook → backend đối chiếu mã đơn + số tiền, đổi đơn thành
   `paid`, cộng credit. Chống xử lý trùng 3 lớp: đơn phải đang `pending`,
   `sepay_transaction_id` UNIQUE, và chỉ nhận giao dịch `transferType = "in"`
   (tiền vào — bỏ qua tiền ra).

API: `GET /payments/pricing`, `GET /payments/credits`, `POST /payments/orders`,
`GET /payments/orders/{id}` (poll trạng thái), `GET /payments/orders` (lịch sử).

#### Bật webhook SePay (chạy thật)

```text
POST https://<domain-cong-khai>/api/v1/payments/sepay/webhook
```

1. Backend phải có `SEPAY_WEBHOOK_SECRET` và `SEPAY_BANK_ACCOUNT` (số TK đầy đủ)
   trong `backend/.env`, sau đó khởi động lại backend.
2. Mở cổng 8000 ra Internet. Dev dùng ngrok:
   `ngrok http 8000` → lấy domain `https://<random>.ngrok-free.app`.
   Không dùng `localhost` (SePay không gọi được).
3. Trong trang quản lý SePay → **Webhooks** → thêm webhook:
   - Loại giao dịch: **Tiền vào**
   - Định dạng: **JSON**
   - URL: `https://<domain-cong-khai>/api/v1/payments/sepay/webhook`
   - Bảo mật: **API Key** (SePay gửi `Authorization: Bearer <key>`) hoặc
     header `X-Webhook-Secret` — điền đúng chuỗi `SEPAY_WEBHOOK_SECRET`.
4. Giao dịch không khớp đơn nào chỉ được log, endpoint luôn trả 2xx để SePay
   không retry.

#### Kiểm thử giao dịch thật

1. Vào **Account → Credits → Mua credit**, chọn gói 100.000₫.
2. Màn thanh toán hiện QR + `NAP DV______`; quét QR bằng app ngân hàng
   (**giữ nguyên nội dung chuyển khoản**).
3. Sau khi chuyển, màn hình tự poll mỗi 4s → chuyển sang "Thanh toán thành công";
   số dư credit tăng đúng gói.
4. Kiểm tra `GET /api/v1/payments/orders` thấy đơn `paid` kèm `paid_at`.
5. Nếu không tự cộng: xem log backend (`SePay webhook: ...`) để biết lý do
   (sai số tiền / thiếu mã đơn / secret sai).

Migration DB thật: `python scripts/migrate_add_credits_payments.py`
(idempotent — thêm cột credit cho `users`, tạo `pricing_packages` +
`payment_orders`, seed gói).

### AI OCR, Key-Value, dịch và chatbot

Sau khi tạo token mới, chỉ đặt token trong `backend/.env` hoặc biến môi trường
server (`ANTHROPIC_AUTH_TOKEN=...`), tuyệt đối không đưa vào Flutter, Git hoặc tin nhắn.
PowerShell local:

```powershell
cd C:\Users\hoang\Downloads\testss\backend
(Get-Content .env) -replace '^ANTHROPIC_AUTH_TOKEN=.*$', 'ANTHROPIC_AUTH_TOKEN=<TOKEN_MOI_CUA_BAN>' |
  Set-Content .env
```

Khởi động lại backend sau khi đổi `.env`; mở `/health` và kiểm tra
`"ai_configured": true`.
Tab **AI** cho phép chọn PDF trong kho để OCR/trích Key-Value, xuất `.docx`, hỏi đáp
theo tài liệu và dịch vùng text được bôi chọn trong viewer. Các endpoint `/api/v1/ai/*` luôn kiểm tra tài liệu
thuộc user hiện tại; khi chưa cấu hình key, backend trả lỗi cấu hình rõ ràng thay vì
giả lập kết quả. Mỗi lượt gọi trừ **50 credit** (`CREDIT_COST_AI`), lỗi AI thì tự hoàn.
