# Phân tích nghiệp vụ Sprint 1 — App quản lý tài liệu đa nền tảng

- **Ngày phân tích:** 2026-10-12
- **Nguồn thông tin:** danh sách 6 sprint do khách đưa (bản duy nhất). **Không có SRS / technical design trong repo.** Repo hiện tại là Flutter template mặc định — đã kiểm chứng: `pubspec.yaml` chỉ có `cupertino_icons` + `flutter_lints`, `lib/main.dart` là counter template, cấu trúc nền tảng scaffold là **android / ios / windows** (⚠ **không có `macos/`**).
- **Phạm vi:** chỉ Sprint 1. Sprint 2–6 chỉ dùng làm bối cảnh out-of-scope.
- Quy ước: **❓** = danh sách sprint không định nghĩa case này → đưa vào mục "Cần xác nhận", không tự chốt.

---

## 1. Tổng quan phạm vi Sprint 1

### 1.1 In-scope (theo nguyên văn danh sách sprint)

| Nhóm | Hạng mục |
|---|---|
| Backend | Khởi tạo server (**FastAPI hoặc Node.js — CHƯA chốt**); thiết kế DB schema PostgreSQL: bảng `users`, `sessions`; tích hợp Google OAuth2 **phía server** (verify token, cấp JWT) |
| Frontend | Khởi tạo **Clean Architecture** (Core, Data, Domain, Presentation); tích hợp `google_sign_in` cho Android, iOS, Desktop; màn hình Đăng nhập; **lưu token bảo mật cục bộ**; UI bộ khung ứng dụng (Shell / Dashboard / Navigation Bar) |

### 1.2 Mâu thuẫn và điểm chưa định nghĩa trong phạm vi (❓)

1. **Mâu thuẫn nền tảng Desktop:** sprint 1 ghi "`google_sign_in` cho Android, iOS, Desktop" nhưng:
   - Package `google_sign_in` **chỉ hỗ trợ chính thức Android, iOS, macOS, web — KHÔNG hỗ trợ Windows/Linux**.
   - Repo hiện chỉ scaffold **Windows** (không có `macos/`).
   - → Nếu "Desktop" = Windows thì `google_sign_in` không dùng được, phải chọn phương án khác (xem **L5**). Đây là quyết định kỹ thuật – nghiệp vụ lớn nhất của Sprint 1.
2. **Refresh token rotation:** sprint không nhắc. Vì đã có bảng `sessions` (nơi duy nhất hợp lý để xoay refresh token), đề xuất làm **rotation cơ bản** trong Sprint 1; cơ chế nâng cao (reuse detection thu hồi toàn bộ) có thể defer. ❓
3. **Logout trên bao nhiêu thiết bị:** sprint không nhắc. Đề xuất Sprint 1 chỉ **logout thiết bị hiện tại** (thu hồi đúng 1 session); "đăng xuất tất cả thiết bị" ❓ defer hoặc làm kèm.
4. **Phương thức đăng nhập:** nguyên văn sprint 1 chỉ có Google OAuth2 → mặc định **không có email/password, không quên mật khẩu, không link account**. ❓ xác nhận phương thức khác không nằm trong toàn bộ lộ trình 6 sprint.
5. **Ai được phép đăng nhập:** Google OAuth2 mặc định cho **mọi account Google** tạo user mới (open registration). Có cần giới hạn domain Workspace / whitelist email không — ❓ sprint không nói, nhưng ảnh hưởng ngay Sprint 1 (bước upsert user).
6. **Profile / quản lý tài khoản hiển thị:** không có trong sprint → out-of-scope Sprint 1 (Shell có thể hiển thị tên/ảnh avatar lấy từ JWT/user, không có màn hình sửa).
7. **Ngôn ngữ UI / branding:** ❓ sprint không nói (xem Cần xác nhận mục 5).

### 1.3 Out-of-scope (thuộc sprint sau hoặc không có trong lộ trình)

| Phạm vi | Ghi chú |
|---|---|
| Sprint 2 | folders, documents, permissions, upload S3/GCS, PDF viewer, gộp/tách/đặt mật khẩu PDF |
| Sprint 3 | AI OCR + trích xuất Key-Value |
| Sprint 4 | Smart Table Extractor, Auto-tagging, Redaction |
| Sprint 5 | PDF Diff + AI Impact Analysis |
| Sprint 6 | RAG Chatbot (pgvector) + hoàn thiện |
| Không có trong lộ trình 6 sprint | Phân quyền RBAC theo role, trang admin quản trị user, invite/whitelist (trừ ❓ mục 1.2.5), đa ngôn ngữ, push notification, multi-tenant. **Không thiết kế schema cho các mục này ở Sprint 1** (YAGNI — thêm khi đến sprint tương ứng). |

---

## 2. Actor và thuật ngữ

**Actor:**
- **Người dùng cuối** — có account Google, dùng app trên Android/iOS/Windows.
- **Google** — Identity Provider (cấp `id_token`, quản lý consent).
- **Backend** — server chưa chốt công nghệ; xác thực, cấp JWT, quản lý session.
- **Flutter client** — app đa nền tảng.
- **PostgreSQL** — lưu `users`, `sessions`.

**Thuật ngữ:**
- **id_token**: JWT do Google cấp sau đăng nhập, client chuyển cho backend để chứng minh danh tính.
- **Access token (JWT)**: do **backend tự cấp**, thời hạn ngắn, client đính kèm mỗi request API.
- **Refresh token**: chuỗi ngẫu nhiên mật độ cao (≥ 256 bit), thời hạn dài, dùng đổi access token mới; server lưu **hash** trong `sessions`.
- **Session**: dòng trong bảng `sessions`, đại diện cho 1 lần đăng nhập trên 1 thiết bị.
- **Secure storage**: `flutter_secure_storage` — Keychain (iOS), Keystore (Android), DPAPI (Windows).

**Trạng thái xác thực của app:** `chưa đăng nhập` → `đang đăng nhập` → `đã đăng nhập` (Shell) → `đang refresh` (trung gian, trong suốt với user) → quay về `chưa đăng nhập` khi logout hoặc session chết.

---

## 3. Breakdown luồng nghiệp vụ

### L1 — Lần đầu mở app → chưa đăng nhập → Login → Shell

**Tóm tắt:** đảm bảo người dùng mới đi từ mở app đến Dashboard an toàn; người cũ được tự động phục hồi phiên (nhánh rẽ sang L3).

**Điều kiện tiên quyết:** app cài đặt xong, có kết nối mạng, backend đã chạy, cấu hình Google OAuth client (client ID) đã nhúng vào app.

**Các bước (happy path):**
1. **User** mở app → **Flutter** khởi động, hiện Splash.
2. **Flutter (AuthRepository)** đọc secure storage: có cặp access/refresh token không? → Lần đầu: **không có**.
3. **Flutter** điều hướng sang **LoginScreen** (màn Đăng nhập + nút "Đăng nhập bằng Google"); Shell/Dashboard chưa render.
4. **User** bấm nút Google → chuyển sang luồng **L2**.
5. L2 thành công → **Flutter** cập nhật trạng thái `đã đăng nhập` → điều hướng **Shell** (Dashboard + Navigation Bar; Sprint 1 Dashboard là khung trống, chưa có dữ liệu nghiệp vụ).

**Nhánh rẽ:**
- Bước 2 **có** token → đi sang **L3** (session restore), không qua màn Login.
- L2 thất bại (hủy, sai token, mạng) → quay lại LoginScreen kèm thông báo lỗi tiếng Việt; trạng thái vẫn `chưa đăng nhập`.

**Kết quả:** user ở Shell; không thay đổi DB trong luồng này (DB chỉ đổi trong L2/L3).

---

### L2 — Đăng nhập Google trên mobile (luồng trọng tâm Sprint 1)

**Tóm tắt:** người dùng đăng nhập bằng Google; backend tự xác minh danh tính (không tin client), upsert user, tạo session, cấp cặp token.

**Điều kiện tiên quyết:** app có `google_sign_in` cấu hình đúng client ID; backend có endpoint xác thực Google (đề xuất `POST /auth/google`); DB có bảng `users`, `sessions`.

**Các bước (happy path):**
1. **User** bấm "Đăng nhập bằng Google" → **Flutter** gọi `google_sign_in`.
2. **Google (SDK)** mở account picker (UI hệ thống) → **User** chọn account (lần đầu: màn consent).
3. **Google** trả về **id_token** (JWT, chứa `sub`, `email`, `name`, `picture`, `aud`, `exp`).
4. **Flutter** gọi `POST /auth/google` với `{id_token, device_info}` (platform, tên máy, phiên bản app).
5. **Backend** xác minh id_token: chữ ký (qua Google JWKS, cache public key), `iss` ∈ {`accounts.google.com`, `https://accounts.google.com`}, `aud` = client ID của **mình**, `exp` còn hạn.
6. **Backend → DB:** upsert `users` theo `google_sub`:
   - Chưa có → **INSERT** user mới (`google_sub`, `email`, `name`, `avatar_url`, timestamps).
   - Đã có → **UPDATE** `email`/`name`/`avatar_url` nếu Google side có thay đổi.
7. **Backend:** sinh **refresh token** ngẫu nhiên ≥ 256 bit → **Backend → DB: INSERT** `sessions` (`user_id`, `refresh_token_hash` = SHA-256, `device_info`, `expires_at`, `revoked_at = NULL`).
8. **Backend → Flutter:** trả **access JWT** (claim: `sub` = user id, `sid` = session id, `exp` ngắn) + refresh token (bản plain chỉ trả đúng 1 lần này duy nhất).
9. **Flutter:** lưu cả hai vào **secure storage**; cập nhật trạng thái `đã đăng nhập`.
10. **Flutter** điều hướng Shell/Dashboard; ghi log phía backend.

**Nhánh rẽ:**
- Bước 5 fail (aud sai / hết hạn / chữ ký sai) → HTTP 401 → client báo lỗi, **không** upsert, **không** tạo session.
- Bước 2 user hủy picker/từ chối consent → `google_sign_in` trả cancel → quay lại LoginScreen **không** báo lỗi đỏ.
- Bước 9 fail (ghi secure storage lỗi) → báo lỗi, không vào Shell (tránh trạng thái "vào app mà không có token").
- Bước 4/8 lỗi mạng / backend chết → xem EC-06, EC-07.

**Kết quả:** `users` có 1 dòng (mới hoặc cập nhật); `sessions` +1 dòng; client có cặp token; user ở Dashboard.

---

### L3 — Mở app lần sau (session restore: token còn / hết hạn / chết)

**Tóm tắt:** người dùng quay lại không phải đăng nhập lại nếu phiên còn sống; hết hạn access thì refresh; refresh chết thì về Login.

**Điều kiện tiên quyết:** secure storage còn token (hoặc biết chắc là không còn); backend có endpoint `POST /auth/refresh`.

**Các bước (happy path — access còn hạn):**
1. **Flutter** khởi động → đọc token từ secure storage.
2. Access token còn hạn (check `exp` client-side, trừ biên an toàn ~60s cho clock skew — xem EC-13) → vào thẳng **Shell**, không gọi mạng nào bắt buộc.

**Các bước (access hết hạn, refresh còn):**
1. Đọc token → access hết hạn.
2. **Flutter** gọi `POST /auth/refresh` với refresh token.
3. **Backend:** hash refresh token nhận được → **DB: SELECT** `sessions` theo `refresh_token_hash`; hợp lệ khi: tồn tại, `revoked_at IS NULL`, `expires_at > now()`.
4. Hợp lệ → **DB:** (nếu có rotation) `UPDATE` session cũ `revoked_at = now()` + **INSERT** session mới, hoặc xoay `refresh_token_hash` ngay trên session hiện có; **cấp** access JWT mới (+ refresh mới nếu rotation).
5. **Flutter** ghi đè cặp token mới vào secure storage → vào Shell. Toàn bộ diễn ra trong suốt với user.

**Nhánh rẽ:**
- Bước 3 **fail** (revoked / hết hạn / không tồn tại) → HTTP 401 → **Flutter xóa token local** → về **LoginScreen** với thông báo "Phiên đăng nhập đã hết hạn, vui lòng đăng nhập lại".
- Bước 2 **lỗi mạng / backend 5xx** → **KHÔNG xóa token, KHÔNG về Login** (phân biệt 401 xác thực với lỗi hạ tầng); hiện màn trạng thái "Không thể kết nối máy chủ — Thử lại". ❓ sprint không định nghĩa chế độ offline; đây là đề xuất an toàn.
- Secure storage rỗng/hỏng → coi như chưa đăng nhập → L1.
- Access còn hạn nhưng bị thu hồi phía server (admin revoke, session bị xoay ở EC-11 nghiêm ngặt) → request API đầu tiên sau đó nhận 401 → interceptor thử refresh → fail → về Login (xem EC-17).

**Kết quả:** user ở Shell với phiên mới, hoặc về Login với local sạch.

---

### L4 — Logout

**Tóm tắt:** kết thúc phiên trên **thiết bị hiện tại**: thu hồi session server + xóa token local + về Login.

**Điều kiện tiên quyết:** user đang `đã đăng nhập`.

**Các bước (happy path):**
1. **User** bấm "Đăng xuất" (trong Shell — ❓ sprint không chỉ định vị trí UI; đề xuất menu tài khoản/cài đặt).
2. **Flutter** gọi `POST /auth/logout` (kèm token định danh session).
3. **Backend → DB:** `UPDATE sessions SET revoked_at = now() WHERE id = {sid} AND revoked_at IS NULL` (điều kiện `IS NULL` để logout idempotent).
4. **Flutter:** gọi `signOut` của `google_sign_in` (đăng xuất app khỏi Google SDK — **không** dùng `disconnect`, để giữ consent, lần sau đăng nhập nhanh).
5. **Flutter:** xóa access + refresh token khỏi secure storage.
6. **Flutter:** điều hướng về LoginScreen; trạng thái về `chưa đăng nhập`.

**Thứ tự 2→5:** đề xuất thực hiện song song có timeout ngắn (3–5s) cho bước 2; **dù bước 2/4 lỗi cũng vẫn chạy bước 5+6** — logout về mặt UX không được phép kẹt. Session server nếu chưa revoke sẽ tự chết khi `expires_at` (chấp nhận rủi ro dư thừa, xem EC-18).

**Nhánh rẽ:**
- Backend chết ở bước 2 → vẫn xóa local + về Login (best-effort revoke), ghi log để dọn session mồ côi bằng cron dọn `sessions` hết hạn.
- Bấm logout 2 lần / logout trên 2 thiết bị đồng thời → idempotent, không lỗi (EC-20, EC-19).

**Kết quả:** session hiện tại `revoked_at` có giá trị; local sạch; về Login. **Không** ảnh hưởng session trên thiết bị khác.

---

### L5 — Đăng nhập trên Windows desktop

**Bối cảnh kỹ thuật đã kiểm chứng:**
- Sprint 1 ghi "google_sign_in cho Android, iOS, Desktop", nhưng package `google_sign_in` **không hỗ trợ Windows/Linux** (chỉ Android/iOS/macOS/web).
- Repo hiện scaffold **Windows** (không có `macos/`).
- → "Desktop" trong Sprint 1 thực chất là **Windows**, và **không thể** dùng `google_sign_in` như mobile. Phải chọn phương án bên dưới (quyết định ở mục Cần xác nhận mục 3).

Điểm chung của mọi phương án: **backend không đổi** — kết thúc luồng vẫn là backend nhận danh tính đã xác minh, upsert user, tạo session, cấp JWT như L2 (bước 5–8 giữ nguyên).

**Phương án (a) — `flutter_appauth`, Authorization Code + PKCE, mở system browser:**
- Cách chạy: app mở trình duyệt hệ thống tới trang Google → user đăng nhập → Google redirect về app qua custom URL scheme → thư viện đổi code lấy token → gửi id_token cho backend như L2.
- **Ưu:** đúng chuẩn OAuth2/OIDC cho native app (theo khuyến nghị RFC 8252); PKCE chống chặn code; token không đi qua URL app thứ ba; một thư viện có thể dùng chung cho Android/iOS luôn; bảo mật tốt nhất trong 3 phương án.
- **Nhược:** phải đăng ký client ID loại desktop/iOS riêng; cấu hình custom URL scheme cho từng nền tảng; Windows cần plugin bắt scheme activation (vd `app_links`) + xử lý second-instance; cấu hình ban đầu phức tạp nhất.

**Phương án (b) — tự làm loopback redirect (local HTTP server + `oauth2` package):**
- Cách chạy: app chạy HTTP server tạm trên `127.0.0.1:{port}` → mở trình duyệt hệ thống → Google redirect về `http://127.0.0.1:{port}/...` → app nhận code, tự đổi lấy token (có PKCE tự cài) → tắt server → gửi id_token cho backend.
- **Ưu:** là pattern Google **chính thức dành cho desktop app** (loopback IP); không cần custom URL scheme; kiểm soát trọn vẹn luồng; phụ thuộc thư viện ít.
- **Nhược:** tự viết nhiều hơn (state, PKCE, parse redirect, tắt server sạch); redirect qua `http://` loopback cần được Google cho phép (đã hỗ trợ sẵn cho desktop client); port động có thể vướng firewall (hiếm, loopback thường miễn).

**Phương án (c) — dán token thủ công hoặc defer Windows:**
- Cách chạy (thủ công): user tự lấy token qua web flow bên ngoài rồi dán vào app; hoặc (defer) Sprint 1 chỉ ship Android/iOS, Windows hẹn sprint sau.
- **Ưu:** chi phí gần bằng 0; không rủi ro kỹ thuật mới.
- **Nhược:** UX không chấp nhận được cho sản phẩm (user thường không biết lấy token); nếu defer thì Sprint 1 không đúng chữ "Desktop" trong danh sách sprint → cần khách chấp nhận đổi phạm vi.

**So sánh nhanh:**

| Tiêu chí | (a) appauth + PKCE | (b) loopback tự làm | (c) thủ công / defer |
|---|---|---|---|
| Bảo mật | Cao nhất | Cao (nếu cài PKCE đúng) | Thấp / N-A |
| Công sức | Trung bình–cao | Trung bình | Gần 0 |
| Phụ thuộc thư viện | 1 package + plugin scheme | `oauth2` + tự viết | Không |
| Tái dùng cho mobile | Có (AppAuth chạy cả iOS/Android) | Không (mobile giữ google_sign_in) | — |
| Đúng phạm vi sprint | Đúng | Đúng | Defer = đổi phạm vi |

**Đề xuất kỹ thuật (chưa chốt):** nếu muốn thống nhất một cơ chế đăng nhập cho cả mobile + desktop thì (a); nếu chỉ cần Windows nhanh và chấp nhận mobile vẫn dùng `google_sign_in` riêng thì (b). Không khuyến nghị (c) trừ khi khách chấp nhận thu hẹp phạm vi Sprint 1.

---

## 4. DB schema đề xuất (PostgreSQL, Sprint 1)

Chỉ 2 bảng đúng như sprint 1 ghi. Không tạo trước bảng của Sprint 2.

### 4.1 Bảng `users`

| Cột | Kiểu | Ràng buộc | Ghi chú |
|---|---|---|---|
| id | UUID | PK, DEFAULT gen_random_uuid() | Dùng làm `sub` trong access JWT — không lộ số liệu nội bộ |
| google_sub | VARCHAR(255) | **NOT NULL, UNIQUE** | **Khóa danh tính chính** từ Google. KHÔNG dùng email làm khóa — email có thể đổi (EC-27) |
| email | VARCHAR(320) | NOT NULL, INDEX (không UNIQUE — xem EC-27) | Chỉ dùng hiển thị/liên hệ |
| name | VARCHAR(255) | NULL | Tên hiển thị từ Google |
| avatar_url | TEXT | NULL | Ảnh đại diện từ Google `picture` |
| created_at | TIMESTAMPTZ | NOT NULL, DEFAULT now() | |
| updated_at | TIMESTAMPTZ | NOT NULL, DEFAULT now() | |

### 4.2 Bảng `sessions`

| Cột | Kiểu | Ràng buộc | Ghi chú |
|---|---|---|---|
| id | UUID | PK | Chính là claim `sid` trong access JWT |
| user_id | UUID | NOT NULL, FK → users(id) ON DELETE CASCADE, **INDEX** | Tìm theo user phục vụ "logout mọi thiết bị" (nếu chốt làm) |
| refresh_token_hash | VARCHAR(64) | **NOT NULL, UNIQUE** | **SHA-256 hex của refresh token. REFRESH TOKEN TUYỆT ĐỐI KHÔNG LƯU PLAINTEXT** — DB lộ thì token vẫn an toàn. Hash một chiều SHA-256 là đủ (token do server sinh ngẫu nhiên 256-bit, không cần bcrypt như password, và UNIQUE index tra cứu nhanh) |
| device_info | JSONB | NULL | Platform, model, app version, IP — phục vụ hiển thị "đăng nhập từ đâu" sau này |
| expires_at | TIMESTAMPTZ | NOT NULL, **INDEX** | Thời điểm refresh token chết; index phục vụ cron dọn session hết hạn |
| revoked_at | TIMESTAMPTZ | NULL | NULL = đang sống. Logout/rotation set giá trị này |
| created_at | TIMESTAMPTZ | NOT NULL, DEFAULT now() | |
| last_used_at | TIMESTAMPTZ | NULL | Cập nhật mỗi lần refresh — phục vụ xóa session cũ nhất khi vượt giới hạn (❓ Cần xác nhận mục 7) |
| updated_at | TIMESTAMPTZ | NOT NULL, DEFAULT now() | |

**Tổng hợp index đề xuất:**
- `users.google_sub` — UNIQUE (đồng thời là index tra cứu upsert).
- `users.email` — INDEX thường.
- `sessions.refresh_token_hash` — UNIQUE (đường nóng nhất: tra cứu khi refresh).
- `sessions.user_id`, `sessions.expires_at` — INDEX (revoke theo user; cron cleanup).

**Ghi chú thiết kế:** access JWT không cần bảng — stateless, tự hết hạn. Mọi trạng thái thu hồi đều nằm ở `sessions` thông qua `sid`.

---

## 5. Edge case tổng hợp (EC-xx)

> Cột "Hành vi đề xuất" là đề xuất của phân tích này khi sprint không định nghĩa; **❓** đánh dấu các case bắt buộc chốt với khách/stakeholder.

### Nhóm L2 — Đăng nhập Google

| Mã | Case | Hành vi đề xuất |
|---|---|---|
| EC-01 | id_token sai `aud` (token của app/client khác, hoặc nhúng nhầm client ID) | Backend 401 "Token không hợp lệ"; không upsert, không tạo session |
| EC-02 | id_token hết hạn (Google cấp hạn 1 giờ; client gửi token cũ trong cache) | Backend 401; client luôn đăng nhập Google lấy token mới ngay trước khi POST để giảm xác suất; nếu vẫn dính → báo lỗi, user bấm lại |
| EC-03 | Chữ ký sai / token giả mạo | Backend 401; log cảnh báo bảo mật (IP, device_info) |
| EC-04 | User hủy account picker / từ chối consent | SDK trả cancel → quay lại LoginScreen **im lặng**, không hiện lỗi đỏ |
| EC-05 | User thu hồi quyền app trên Google Account (myaccount.google.com) giữa phiên | Backend **không biết** — refresh token phía mình vẫn hợp lệ. Đề xuất: chấp nhận độ trễ (access ngắn hạn + refresh có hạn tự giới hạn rủi ro); ❓ có muốn kiểm tra Google tokeninfo khi refresh không (tốn 1 call ngoài) |
| EC-06 | Mất mạng ngay sau khi có id_token, trước khi POST backend | Client báo "Không có kết nối mạng", giữ LoginScreen; **không** mất gì — đăng nhập lại từ đầu |
| EC-07 | Backend chết/timeout sau khi đã tạo session nhưng trước khi response về client (session "mồ côi": DB có session, client không có token) | Client báo lỗi, user thử lại → login lại tạo session **mới** (upsert user idempotent theo `google_sub`, không duplicate user). Session mồ côi chết theo `expires_at` → cron dọn. Chấp nhận, không cần xử lý đặc biệt |
| EC-08 | Google trả `email_verified = false` | Đề xuất: backend từ chối (401 "Email Google chưa xác minh"). ❓ sprint không nói |
| EC-09 | User chọn account Google Workspace bị chính sách chặn app của tổ chức | Google SDK tự báo lỗi trước khi có token; client hiển thị lỗi gốc của Google |
| EC-10 | id_token hợp lệ nhưng là token của 1 client ID khác (lỗi cấu hình dev/prod) | Trùng EC-01 — chặn bằng check `aud`; ghi chú cấu hình client ID theo flavor |
| EC-32 | `device_info` client gửi quá dài / sai định dạng | Backend truncate về giới hạn cột; không bao giờ lỗi 500 vì dữ liệu hiển thị |

### Nhóm L3 — Session restore / refresh

| Mã | Case | Hành vi đề xuất |
|---|---|---|
| EC-11 | **Refresh race giữa 2 thiết bị / 2 process** trên cùng refresh token (retry do timeout, copy storage) | Nếu có rotation: request 2 thấy token đã revoked → cần phân biệt **retry vô hại** vs **reuse (dấu hiệu đánh cắp)**. Đề xuất: grace period ngắn (30–60s token cũ vẫn đổi được) HOẶC nghiêm ngặt: reuse → revoke toàn bộ session của user. ❓ mức độ chốt với khách |
| EC-12 | Refresh token hết hạn tự nhiên (`expires_at` quá khứ) | 401 → xóa local → về Login "Phiên hết hạn, đăng nhập lại" |
| EC-13 | **Clock skew**: giờ máy client sai so với server | Client-side: mọi check `exp` trừ leeway 60s (còn < 60s coi như hết hạn → chủ động refresh). Server-side: đồng hồ server là chuẩn tuyệt đối, không tin claim từ client ngoài chữ ký |
| EC-14 | Secure storage bị xóa (clear data, gỡ cài đặt, logout gián đoạn) | Client coi như chưa đăng nhập → Login. Session cũ trong DB sống tới `expires_at` → cron dọn; ❓ có giới hạn số session/user không (Cần xác nhận mục 7) |
| EC-15 | User đổi giờ hệ thống trong lúc dùng app | Trùng EC-13 — leeway che được skew nhỏ; skew lớn → access tính là hết hạn → refresh → server cấp token mới, trạng thái tự hồi phục |
| EC-16 | Refresh gặp **5xx / timeout** (backend chết) | **Không xóa token, không về Login** (phân biệt rõ 401 xác thực vs lỗi hạ tầng); màn "Không thể kết nối — Thử lại"; giữ token thử lại lần sau |
| EC-17 | Access còn hạn nhưng session đã bị thu hồi phía server (admin, rotation ở EC-11 nghiêm ngặt) | Request API đầu nhận 401 → interceptor tự refresh → fail → về Login kèm thông báo. User chỉ thấy một lần đăng nhập lại |
| EC-31 | **Burst 401**: access vừa hết hạn, nhiều request song song cùng nhận 401 → nhiều luồng cùng gọi refresh | **Single-flight refresh** ở client: chỉ 1 request refresh duy nhất, các request khác đợi kết quả rồi dùng token mới; bắt buộc để không tự gây EC-11 |

### Nhóm L4 — Logout

| Mã | Case | Hành vi đề xuất |
|---|---|---|
| EC-18 | Logout khi backend chết (không revoke được trên server) | Vẫn xóa local + về Login (UX không kẹt); session server sống tới `expires_at` — chấp nhận vì access ngắn hạn; log lại để đối soát |
| EC-19 | Logout bị gián đoạn (crash sau bước server revoke, trước khi xóa local) | Mở app lại: token còn local → L3 refresh → backend trả 401 (đã revoked) → tự xóa local → Login. Trạng thái tự hồi phục |
| EC-20 | Double-tap logout / logout gọi 2 lần | Idempotent: `UPDATE ... WHERE revoked_at IS NULL` giữ giá trị đầu; client disable nút trong lúc xử lý |
| EC-21 | `signOut` Google SDK lỗi giữa lúc logout | Best-effort: bỏ qua lỗi, vẫn xóa token local + về Login; ghi log |
| EC-33 | Logout khi đang có request API đang bay | Cho request cũ chết tự nhiên (401 bỏ qua sau khi đã logout — interceptor check cờ `isLoggingOut` để không kích hoạt refresh) |

### Nhóm L5 — Windows desktop

| Mã | Case | Hành vi đề xuất |
|---|---|---|
| EC-22 | Máy không có browser mặc định / browser không mở được | Báo lỗi "Không mở được trình duyệt để đăng nhập" + hướng dẫn; không crash |
| EC-23 | (Phương án b) port loopback bị chiếm | Sinh port động ngẫu nhiên khi bắt đầu flow, retry lần khác |
| EC-24 | User để trang Google mở quá lâu (state/PKCE verifier hết hạn, đề xuất 10 phút) | Trang redirect trả thông báo hết hạn trên local server → app báo "Đã quá thời gian đăng nhập, thử lại" |
| EC-25 | (Phương án a) Custom scheme kích hoạt **instance thứ hai** của app | Forward payload sang instance đang chạy (single-instance + `app_links`), instance 2 tự thoát |
| EC-26 | Nhiều user Windows khác nhau dùng chung máy | Secure storage của OS theo user profile → tự tách, không cần xử lý gì |

### Nhóm chéo — dữ liệu, đồng thời, hệ thống ngoài

| Mã | Case | Hành vi đề xuất |
|---|---|---|
| EC-27 | **Email đổi trên Google side**: id_token trả email mới, `google_sub` giữ nguyên | Upsert theo `google_sub` → **không tạo user mới**, UPDATE email. Đây là lý do chính để `email` không UNIQUE; nếu đặt UNIQUE, user có thể bị chặn đăng nhập vô lý. ❓ chốt theo đề xuất này |
| EC-28 | Cùng 1 Google account đăng nhập nhiều thiết bị | Mỗi thiết bị 1 session độc lập — hoạt động song song bình thường; ❓ giới hạn số session (Cần xác nhận mục 7) |
| EC-29 | Session hết hạn **đúng lúc đang dùng app** (mở app lâu, không tắt) | Request đầu sau hết hạn nhận 401 → EC-17: refresh trong suốt; refresh fail mới về Login "Phiên hết hạn". User không bị văng app đột ngột |
| EC-30 | Refresh token bị đánh cắp (thiết bị root/jailbreak, storage bị đọc) | Phòng thủ duy nhất khả thi trong Sprint 1 = rotation + chính sách reuse ở EC-11. Ghi nhận rủi ro, không có giải pháp tuyệt đối ở lớp này |
| EC-34 | Access JWT bị sửa `sub`/`exp` bởi client | Chữ ký của backend chặn — verify chữ ký trước mọi claim khác; 401 |
| EC-35 | Ai cũng có account Google → app thành open registration, bất kỳ ai cũng tự tạo user | Mặc định sprint 1 không có cơ chế chặn. ❓ có cần giới hạn domain/whitelist không (Cần xác nhận mục 6) — quyết định này ảnh hưởng ngay bước upsert |
| EC-36 | 2 lần đăng nhập gần như đồng thời từ 2 thiết bị (upsert + insert song song) | `google_sub` UNIQUE chặn duplicate user (insert thứ 2 → conflict → chuyển thành update); 2 session vẫn tách biệt bình thường |

**Nhóm không áp dụng Sprint 1 (ghi rõ để sau này không quên rà lại):** edge case về file/PDF (Sprint 2), OCR (Sprint 3), bảng/redaction (Sprint 4), diff (Sprint 5), chatbot/vector (Sprint 6) — N/A tại thời điểm này.

---

## 6. Cần xác nhận (quyết định của stakeholder trước khi code)

> Mục này liệt kê **phương án + trade-off**, KHÔNG chốt thay người quyết định.

**1. Backend: FastAPI (Python) hay Node.js (NestJS/Express)?**
- **Node.js (NestJS hoặc Express + TypeScript):** với team 1 junior front-end (quen React/TS), rào cản thấp nhất — cùng ngôn ngữ, cùng hệ sinh thái package, tài liệu nhiều; NestJS cho cấu trúc module tương đồng Clean Architecture của Flutter. Nhược: TypeScript cần kỷ luật; hệ sinh thái auth phải tự lắp nhiều mảnh.
- **FastAPI (Python):** tự sinh OpenAPI docs, Pydantic validate đầu vào rất gọn, thư viện verify Google token (`google-auth`) chính thức, gọn. Nhược: nếu chưa biết Python thì đường cong học + rủi ro lỗi async Python với người mới.
- Trade-off cốt lõi: tốc độ có người dev đi ngay (Node) vs công cụ xác thực/validate sẵn mạnh (FastAPI).

**2. PostgreSQL: Docker hay cài native Windows?**
- **Docker Desktop:** môi trường sạch, reset nhanh, schema migration tái lập được, gần với deploy sau này. Nhược: cần WSL2 + RAM (~2GB cho DB); Windows 10 Home chỉ chạy Docker qua WSL2 backend.
- **Native installer (EDB):** nhẹ hơn, cài một lần dùng luôn, ít lớp công nghệ hơn cho người mới. Nhược: khó reset sạch, nâng version thủ công, môi trường dev khác môi trường prod.
- Trade-off: tái lập được (Docker) vs nhẹ máy và đơn giản vận hành hằng ngày (native).

**3. Windows desktop login: phương án nào ở L5?**
- (a) `flutter_appauth` + PKCE: bảo mật cao nhất, chuẩn RFC 8252, tái dùng được cho mobile; công sức cấu hình cao nhất.
- (b) Loopback + `oauth2`: pattern chính thức của Google cho desktop, không cần custom scheme; tự viết nhiều hơn, mobile vẫn đi `google_sign_in` riêng.
- (c) Dán token thủ công / defer Windows: gần như không tốn công; UX kém / thu hẹp phạm vi Sprint 1 so với danh sách sprint gốc.

**4. Quy tắc JWT (thời hạn + rotation)?**
- Đề xuất làm mốc thảo luận: **access 15 phút** (ngắn để thu hồi nhanh), **refresh 30 ngày tuyệt đối** (không gia hạn vô hạn), **rotation ON ngay Sprint 1** (vì đã có bảng `sessions`), kèm chính sách reuse theo EC-11 (grace period hay revoke-all). Cần chốt: con số + có rotation ngay không.

**5. Tên app / branding hiển thị trên UI?**
- Sprint 1 đã có màn Login + Shell — cần tên hiển thị, icon, và ngôn ngữ UI (tiếng Việt / tiếng Anh / song song). Ảnh hưởng: package name (applicationId), tên cửa sổ Windows, asset icon, văn bản trên Login. Chưa chốt thì phải dùng tên tạm, thay muộn sẽ tốn công đổi cấu hình nền tảng.

**6. (bổ sung) Ai được phép đăng nhập?**
- Mở cho mọi account Google (mặc định hiện tại) vs giới hạn domain Google Workspace vs whitelist email. Trade-off: mở rộng = ai cũng dùng được nhưng không kiểm soát; giới hạn = chặn bằng 1 check `hd`/email ngay bước verify, công gần bằng 0 nhưng cần danh sách domain từ khách. (EC-35)

**7. (bổ sung) Giới hạn session mỗi user + dọn dẹp?**
- Không giới hạn: đơn giản nhất nhưng `sessions` phình vô hạn (mỗi lần cài lại app +1 dòng). Giới hạn N session (vd 10, xóa `last_used_at` cũ nhất) + cron xóa session hết hạn: sạch nhưng thêm 1 job + chính sách. ❓ chốt N hay bỏ giới hạn ở Sprint 1.

---

*Hết phân tích Sprint 1. Các quyết định ở mục 6 được chốt xong sẽ cập nhật lại tài liệu này thành baseline trước khi vào code.*
