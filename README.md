# DocuVault — quản lý tài liệu + AI (Flutter + FastAPI)

Ứng dụng đa nền tảng (web/desktop/mobile) kiểu "Google Drive + AI": kho tài liệu,
công cụ PDF, OCR, so sánh hợp đồng, chatbot RAG. Hiện hoàn thành **Sprint 1 (đăng nhập) + Sprint 2 (kho tài liệu & công cụ PDF)**.

## Yêu cầu máy

- Python 3.12 (đã có venv sẵn tại `backend/.venv`)
- Flutter SDK (máy này đặt ở `C:\Users\hoang\flutter`)
- Docker Desktop (tùy chọn — chỉ cần khi muốn chạy PostgreSQL thật; demo dùng SQLite)

## Cách chạy (PowerShell)

### 1. Chạy backend

```powershell
cd C:\Users\hoang\Downloads\testss\backend
# Lần đầu: tạo DB (dùng SQLite nếu không có Postgres/Docker)
$env:DATABASE_URL = "sqlite:///./docuvault.db"
$env:ALLOW_DEV_LOGIN = "true"          # bật đăng nhập nhanh cho dev/demo
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

Kiểm tra: mở `http://localhost:8000/health` → `{"status":"ok","dev_login":true}`.

> Muốn dùng PostgreSQL thật: bật Docker Desktop → `docker compose up -d` (ở gốc repo) → bỏ `$env:DATABASE_URL` (backend mặc định trỏ Postgres `docuvault:docuvault@localhost:5432`) → chạy lại `alembic upgrade head`.

### 2. Chạy app Flutter (web — máy này chỉ chạy được Edge)

Mở terminal thứ hai:

```powershell
cd C:\Users\hoang\Downloads\testss
$env:Path = "C:\Users\hoang\flutter\bin;$env:Path"
flutter run -d edge
```

- Đăng nhập: tab mở ra → nhập email + tên → **"Vào ứng dụng"** (dev login, không cần mật khẩu).
- Tab **Tài liệu**: "Tải lên" (chọn file, xem tiến độ), "Thư mục mới", chip thư mục để lọc,
  menu ⋮ mỗi file: **Tải xuống / Tách trang / Đặt mật khẩu / Gỡ mật khẩu / Xóa**,
  nút **"Chọn để gộp"**: tích ≥2 PDF → đặt tên → gộp thành file mới (bản gốc giữ nguyên).

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
  app/api/v1/            auth, folders, documents
  app/services/          auth, storage (đĩa cục bộ), pdf (pypdf)
  migrations/            0001 users+sessions, 0002 folders+documents+permissions
  tests/                 pytest (71 test)
lib/                     Flutter Clean Architecture
  core/                  config, lỗi, Dio + interceptor refresh token, file saver
  domain/                entities + repository interfaces
  data/                  models + repository impl
  presentation/          Riverpod controllers + screens (Login, Shell, Documents)
docs/                    phân tích nghiệp vụ sprint 1
```

## Đăng nhập Google thật (khi sẵn sàng — cần tài khoản Google)

1. https://console.cloud.google.com → tạo project.
2. **APIs & Services → OAuth consent screen**: External, điền app name + email.
3. **Credentials → Create credentials → OAuth client ID** ×4:
   - **Web application**: Authorized JavaScript origins `http://localhost:8000` (cổng backend nếu verify server-side) — lấy *Client ID*.
   - **Android**: package name = applicationId của app, SHA-1 từ `keytool -list -v -keystore ~/.android/debug.keystore -alias androiddebugkey -storepass android`.
   - **iOS**: Bundle ID của app.
   - **Desktop app**: cho luồng loopback trên Windows.
4. Truyền client ID khi chạy app:
   ```powershell
   flutter run -d edge --dart-define=GOOGLE_WEB_CLIENT_ID=xxxx.apps.googleusercontent.com
   ```
5. Backend cần biến `GOOGLE_CLIENT_IDS` chứa các client ID (phân cách bởi dấu phẩy) để verify `aud`.

Lưu ý: hiện app dùng **dev login** (không mật khẩu) để demo nhanh; luồng Google
(google_sign_in 7.x trên mobile, loopback+PKCE trên desktop) đã code sẵn trong
`lib/core/auth/` — chỉ còn wire vào màn Login khi có client ID.

## Biến môi trường backend (`.env` hoặc set thủ công)

| Biến | Ý nghĩa | Mặc định |
|---|---|---|
| `DATABASE_URL` | Postgres hoặc `sqlite:///./ten.db` | Postgres local |
| `JWT_SECRET` | Khóa ký JWT (≥32 ký tự) | bắt buộc |
| `GOOGLE_CLIENT_IDS` | Danh sách client ID cho verify | bắt buộc |
| `ALLOW_DEV_LOGIN` | Bật `POST /api/v1/auth/dev` | `false` |
| `ACCESS_TOKEN_MINUTES` / `REFRESH_TOKEN_DAYS` | Tuổi token | 15 / 30 |
| `ALLOWED_EMAIL_DOMAINS` | Chặn domain (rỗng = mở) | rỗng |
| `CORS_ORIGINS` | Origin web được gọi API | rỗng |
| `DOCUMENTS_DIR` | Thư mục lưu file upload | `backend/storage/documents` |
| `MAX_UPLOAD_MB` | Giới hạn 1 file | 50 |
