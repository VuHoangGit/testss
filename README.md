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
cd C:\Users\hoang\Downloads\DocVaultProject\backend
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
cd C:\Users\hoang\Downloads\DocVaultProject
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
cd C:\Users\hoang\Downloads\DocVaultProject\backend
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .

# Flutter
cd C:\Users\hoang\Downloads\DocVaultProject
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

1. Trong Google Cloud Console, project chứa OAuth client phải để **OAuth consent
   screen → User type = External** (KHÔNG phải Internal) — xem mục lỗi 403 bên dưới.
2. Supabase Dashboard → **Authentication → Providers → Google** → bật và dán
   *Client ID* / *Client Secret* lấy từ
   [Google Cloud Console](https://console.cloud.google.com) (Credentials → OAuth client ID).
3. Trong Google Cloud, thêm **Authorized redirect URI**:
   `https://<project-ref>.supabase.co/auth/v1/callback`.
4. Client chỉ cần bấm "Continue with Google" — Supabase trả access token, backend
   verify như mọi token khác.

### Lỗi 403 `org_internal` — "project chỉ dùng được trong tổ chức sở hữu ứng dụng"

Trang `accounts.google.com` chặn trước khi quay về app, nghĩa là OAuth consent
screen đang ở **User type = Internal** (chỉ tài khoản trong tổ chức Google
Workspace sở hữu project đăng nhập được; Gmail thường bị chặn). Sửa:

Kiểm tra nhanh (30 giây): bấm "Continue with Google" rồi chọn một tài khoản
**cùng tổ chức Workspace sở hữu project** (vd `@fpt.edu.vn` nếu project tạo bằng
tài khoản trường). Vào được ⇒ đúng là consent screen đang Internal.

1. Mở Google Cloud Console **bằng chính tài khoản đã tạo project** (project chỉ
   hiện với tài khoản/tổ chức sở hữu) → **APIs & Services → OAuth consent screen**.
2. **User type** → **External** → Save. Nếu mục này bị khoá (Google không cho
   đổi chiều Internal → External) thì làm theo cách tạo project mới ở dưới.
3. Mục **Publishing status** → **Publish app** (đưa về *In production*). Chỉ dùng
   scope `openid/email/profile` nên không phải xin Google xác minh.
   - Kẹt ở *Testing* thì chỉ tối đa 100 email trong **Test users** đăng nhập được;
     thêm Gmail cần test vào danh sách này cũng chạy ngay.
4. Giữ nguyên Client ID/Secret đã dán ở Supabase, redirect URI
   `https://<project-ref>.supabase.co/auth/v1/callback` không đổi → thử lại.

Nếu project GCP nằm trong tổ chức Workspace không có quyền đổi consent screen:
tạo project mới bằng chính tài khoản Gmail cá nhân (project cá nhân luôn là
External) → tạo OAuth client mới → dán Client ID/Secret mới vào Supabase.

### Đặt tên hiển thị sau lần đăng nhập đầu tiên

`/auth/me` trả thêm `name_chosen_at`:

- `null` = người dùng **chưa tự đặt tên** → app hiện màn *"What should we call
  you?"* ngay sau khi đăng nhập (Google hay email đều vậy), ô nhập điền sẵn tên
  Google làm gợi ý; đặt xong mới vào app chính.
- Có giá trị = đã đặt → vào thẳng app, và tên trong token Google **không** ghi
  đè lựa chọn của người dùng ở các lần đăng nhập sau.

Lưu tên: `PATCH /api/v1/auth/me` với body `{"name": "..."}` (rỗng → 422).

Migration DB thật: `python scripts/migrate_add_name_chosen_at.py` (idempotent) —
**chạy một lần** trên DB đang có dữ liệu; thiếu cột thì mọi API đọc bảng `users`
sẽ lỗi `no such column`.

## Lịch sử phiên bản tài liệu (Version History + AI Compare)

Upload bản mới của cùng một tài liệu mà **không mất bản cũ**: bản hiện tại được
hạ thành phiên bản (giữ tối đa 10 bản, FIFO), khôi phục bản cũ chỉ đổi con trỏ
file. So sánh 2 bản = diff dòng cục bộ (miễn phí) + tóm tắt thay đổi bằng AI
(tốn 1 credit, hoàn nếu lỗi; 2 bản giống nhau → không trừ credit).

- Menu tài liệu → **Version history…**: upload bản mới (kèm ghi chú), restore,
  xóa bản cũ, Compare with current (diff xanh/đỏ + tóm tắt AI tiếng Việt).
- API: `POST /documents/{id}/versions` (upload bản mới) · `GET …/versions`
  (list) · `GET …/versions/{vid}/download` · `POST …/versions/{vid}/restore`
  · `DELETE …/versions/{vid}` · `POST …/versions/diff`.
- Giới hạn: 10 bản/tài liệu; upload bản mới phải cùng loại file (MIME) với
  bản hiện tại; quota đĩa tính cả các bản cũ (không lách được qua lịch sử).
- Compare cần nội dung có lớp text (PDF/Word/txt) — file scan chưa OCR sẽ
  được hướng dẫn chạy OCR trước.

Migration DB thật: `python scripts/migrate_add_document_versions.py`
(idempotent) — chạy một lần trên DB đang chạy; thiếu bảng thì API versions
trả 500 `no such table: document_versions`.

## Biến môi trường backend (`.env` hoặc set thủ công)

| Biến | Ý nghĩa | Mặc định |
|---|---|---|
| `SUPABASE_URL` | URL project Supabase (backend verify token qua JWKS) | **bắt buộc** |
| `DATABASE_URL` | Postgres hoặc `sqlite:///./ten.db` | Postgres local |
| `ALLOWED_EMAIL_DOMAINS` | Chặn domain (rỗng = mở) | rỗng |
| `CORS_ORIGINS` | Origin web được gọi API | rỗng |
| `ENVIRONMENT` | `dev` hoặc `production` (production tắt CORS regex LAN, bật HSTS) | `dev` |
| `TRUSTED_HOSTS` | Host hợp lệ ở header `Host` (chống DNS rebinding), `*` = tắt | `*` |
| `DOCUMENTS_DIR` | Thư mục lưu file upload | `backend/storage/documents` |
| `MAX_UPLOAD_MB` | Giới hạn 1 file | 50 |
| `ALLOWED_UPLOAD_TYPES` | Đuôi file được upload (MIME do server quyết định) | pdf,doc,docx,xls,xlsx,ppt,pptx,txt,md,jpg,jpeg,png,gif,zip |
| `USER_STORAGE_QUOTA_MB` | Tổng dung lượng tài liệu/user (`0` = không giới hạn) | 1024 |
| `RATE_LIMIT_ENABLED` | Bật giới hạn tần suất gọi API | `true` |
| `RATE_LIMIT_AI_PER_MINUTE` | Số lượt gọi AI/phút/user | 60 |
| `RATE_LIMIT_UPLOAD_PER_MINUTE` | Số lượt upload/phút/user | 30 |
| `RATE_LIMIT_ORDERS_PER_MINUTE` | Số lượt tạo đơn nạp/phút/user | 20 |
| `ANTHROPIC_AUTH_TOKEN` | Token dịch vụ AI (API tương thích Anthropic), chỉ đặt ở backend | rỗng |
| `ANTHROPIC_BASE_URL` | Base URL dịch vụ AI | `https://api.z.ai/api/anthropic` |
| `ANTHROPIC_MODEL` | Model cho OCR/chat/dịch | `glm-4.6` |
| `ANTHROPIC_TIMEOUT_SECONDS` | Timeout gọi AI | 90 |
| `OCR_MAX_PAGES` | Số trang tối đa mỗi lượt OCR (mỗi trang 1 lượt gọi AI) | 20 |
| `OCR_DPI` | DPI render trang PDF scan trước khi gửi AI | 200 |
| `OCR_VISION_MODEL` | Model đọc **ảnh** cho trang scan (rỗng = dùng `ANTHROPIC_MODEL`) | rỗng |
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

Gói nạp (bảng `pricing_packages`, seed idempotent): 10.000₫ → 50 credit,
100.000₫ → 1.000 credit, 200.000₫ → 2.500 credit, 500.000₫ → 10.000 credit.
Gói 10.000₫ vừa đủ 1 lượt gọi AI (50 credit) — dùng để nạp thử / chuyển khoản
thật với số tiền nhỏ. Thêm gói mới: sửa `DEFAULT_PACKAGES` trong
`app/services/payment_service.py` (seed theo `code`, không cần migration).

Luồng thanh toán:

1. App gọi `POST /api/v1/payments/orders` tạo đơn → mã đơn `DVXXXXXX` +
   nội dung chuyển khoản `NAP DVXXXXXX` + URL ảnh QR.
   Ảnh QR lấy từ **`https://qr.sepay.vn/img`** (trả PNG — `img.vietqr.io` chỉ
   trả SVG nên `Image.network` của Flutter không vẽ được). `qr_url` được
   **tính lại mỗi lần đọc** từ số tiền + nội dung + cấu hình, không dùng giá trị
   đã lưu trong DB — nên sửa `SEPAY_BANK_ACCOUNT` là các đơn đang chờ hiện QR
   đúng ngay. Chưa điền `SEPAY_BANK_ACCOUNT` thì `qr_url = null`, app chỉ hiện
   thông tin dạng chữ.
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
   - Bảo mật: **API Key** — dán đúng chuỗi `SEPAY_WEBHOOK_SECRET`.
     Lưu ý: ở chế độ này SePay gửi header **`Authorization: Apikey <key>`**
     (scheme `Apikey`, **không phải** `Bearer`). Backend nhận cả `Apikey`,
     `Bearer` và header `X-Webhook-Secret`.
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
cd C:\Users\hoang\Downloads\DocVaultProject\backend
(Get-Content .env) -replace '^ANTHROPIC_AUTH_TOKEN=.*$', 'ANTHROPIC_AUTH_TOKEN=<TOKEN_MOI_CUA_BAN>' |
  Set-Content .env
```

Khởi động lại backend sau khi đổi `.env`; mở `/health` và kiểm tra
`"ai_configured": true`.
Tab **AI** cho phép chọn PDF trong kho để OCR/trích Key-Value, xuất `.docx`, hỏi đáp
theo tài liệu và dịch vùng text được bôi chọn trong viewer. Các endpoint `/api/v1/ai/*` luôn kiểm tra tài liệu
thuộc user hiện tại; khi chưa cấu hình key, backend trả lỗi cấu hình rõ ràng thay vì
giả lập kết quả. Mỗi lượt gọi trừ **50 credit** (`CREDIT_COST_AI`), lỗi AI thì tự hoàn.

**OCR chạy theo từng trang** (xem [docs/ocr-pipeline.md](docs/ocr-pipeline.md)):
PDF có lớp text dùng luôn văn bản trích được (không gọi AI), trang scan mới render
ảnh 200 DPI gửi model đọc — mỗi lượt một trang nên biết sai ở trang nào và một
trang hỏng không làm hỏng cả file. Prompt 3 tầng (luật chép tài liệu → ngữ cảnh
trang → schema JSON cố định), `temperature = 0`, kèm **hậu kiểm bằng máy** (ngày
tháng, số tiền, số CCCD/MST) trả về danh sách `warnings` để người dùng đối soát.
Cài thêm 2 package render PDF: `pip install -r backend/requirements.txt`
(`pypdfium2`, `Pillow`).

**Chụp ảnh trang giấy bằng điện thoại**: tab AI → OCR có nút **"Scan with
camera"** (Android/iOS mở app Camera; web trên điện thoại mở thẳng camera). Ảnh
được thu về cạnh dài ≤ 2400px ngay trên máy, lưu thành tài liệu trong kho (thấy
trong tab Files, xuất Word được) rồi OCR ngay. Server xoay theo EXIF, hạ cạnh dài
về 2000px và nén JPEG trước khi gửi model — ảnh 12 MP không bị vượt giới hạn
request. Chi tiết:
[docs/ocr-pipeline.md](docs/ocr-pipeline.md#10-ảnh-chụp-từ-điện-thoại--luồng-quét).

**Trang scan cần model đọc được ảnh**: `OCR_VISION_MODEL=deepseek-v4-pro` đã được
kiểm chứng trên gateway hiện tại (khớp ~99% so với chữ gốc); model văn bản
`ANTHROPIC_MODEL` không nhận ảnh nên hai việc dùng hai model khác nhau. Chi tiết:
[docs/ocr-pipeline.md](docs/ocr-pipeline.md#6-model-vision--deepseek-v4-pro-đã-kiểm-chứng).

## Bảo mật — những gì backend đang chặn

| Lớp | Cơ chế |
|---|---|
| Xác thực | Verify JWT Supabase qua JWKS (chỉ RS256/ES256, check `iss`/`aud`/`exp`) — không nhận token tự ký |
| Phân quyền | Mọi endpoint tài liệu/folder/AI/đơn nạp kiểm tra `owner_id`; truy cập chéo trả **404** (không lộ sự tồn tại) |
| Giới hạn tần suất | Cửa sổ trượt 60 giây theo user cho `/ai/*`, upload và tạo đơn nạp → **429** + `Retry-After` |
| Upload | Đọc theo chunk, vượt `MAX_UPLOAD_MB` là **413** ngay (không nạp cả file vào RAM); chỉ nhận đuôi trong `ALLOWED_UPLOAD_TYPES`; MIME do **server** quyết định theo đuôi |
| Dung lượng | Tổng dung lượng/user ≤ `USER_STORAGE_QUOTA_MB`; xem mức dùng ở `GET /api/v1/documents/usage` |
| Tải file | MIME lạ ép `application/octet-stream` + `nosniff` (không render HTML trên origin API) |
| Header | `X-Content-Type-Options`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, HSTS khi `ENVIRONMENT≠dev` |
| CORS | Chỉ origin trong `CORS_ORIGINS` + regex localhost/LAN **chỉ khi dev** |
| Webhook SePay | `compare_digest` với `SEPAY_WEBHOOK_SECRET`, chỉ nhận `transferType=in`, đối chiếu số tiền + `accountNumber` (khi đã cấu hình), chống replay bằng UNIQUE `sepay_transaction_id` |

### Checklist trước khi chạy production

1. `ENVIRONMENT=production`, khai báo `CORS_ORIGINS` và `TRUSTED_HOSTS` thật.
2. Chạy sau reverse proxy **HTTPS** (backend chỉ nói HTTP).
3. `SEPAY_WEBHOOK_SECRET` là chuỗi dài ngẫu nhiên; `SEPAY_BANK_ACCOUNT` khớp tài khoản nhận.
4. Supabase Dashboard → Authentication: bật **Confirm email**, mật khẩu tối thiểu 8,
   **Leaked password protection**, bật CAPTCHA; giữ bật **RLS** nếu project có bảng nghiệp vụ.
5. Build release Android: bỏ `android:usesCleartextTraffic="true"` trong `AndroidManifest.xml`.
6. Cân nhắc thêm CAPTCHA/giới hạn theo IP khi mở đăng ký công khai — mỗi tài khoản mới
   có 300 credit free (6 lượt gọi AI), farm tài khoản = tiền thật.
