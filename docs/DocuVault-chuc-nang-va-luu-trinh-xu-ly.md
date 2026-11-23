# DocuVault — Tổng quan chức năng & luồng xử lý

> Ứng dụng quản lý tài liệu + AI đa nền tảng (Flutter web/desktop/mobile · FastAPI · Supabase Auth · SQLite/PostgreSQL) — bản mô tả đơn giản, tổng hợp từ mã nguồn thực tế của dự án.

## 1. Kiến trúc tổng thể

- **Client (Flutter, Clean Architecture + Riverpod)** — màn hình: Login, Shell (4 tab), Documents, AI (OCR/Translate/Chat), Voice, Forms, Payments, Shared view.
- **Backend (FastAPI + SQLAlchemy, prefix `/api/v1`)** — routers: `auth, folders, documents, versions, ai, forms, payments, public_shares`; services: storage (đĩa), pdf (pypdf), ai (Gemini), credit, payment, share, form, pdf_to_docx, voice_command.
- **Dịch vụ ngoài:** Supabase Auth (đăng nhập email/mật khẩu + Google, JWKS verify token) · Gemini API (AI) · SePay (thanh toán) · LibreOffice (doc→docx, khi có).

**Luồng chung của mọi request API:** Flutter (Dio + interceptor tự refresh token) → FastAPI → dependency `CurrentUser` verify JWT với JWKS của Supabase → load/sửa dữ liệu qua SQLAlchemy → trả JSON (hoặc file stream). Các route public share bỏ qua auth, thay bằng rate limit theo IP.

## 2. Chức năng chính & luồng xử lý

### 2.1. Đăng nhập & tài khoản (Supabase Auth)

- **Đăng nhập/đăng ký:** client gửi email/mật khẩu (hoặc Google OAuth) trực tiếp tới **Supabase Auth** → nhận access + refresh token → lưu phiên.
- **Lần đầu vào app:** backend `PATCH /auth/me` lấy/đặt tên hiển thị (màn "Đặt tên" hiện khi chưa có).
- **Mọi lời gọi API:** access token kèm header → backend verify chữ ký qua JWKS → xác định user (bảng `users` đồng bộ theo user_id Supabase).
- **Hết hạn token:** Dio interceptor tự gọi Supabase refresh rồi thử lại request — người dùng không phải đăng nhập lại.

### 2.2. Kho tài liệu (thư mục, tải lên, viewer)

- **Tải lên:** chọn file → client upload (multipart) → backend lưu file vào thư mục đĩa (`storage_service`) + tạo bản ghi `documents` (kèm folder, kích thước, loại) → danh sách tự refresh, có tiến độ.
- **Quản lý:** tạo/xóa thư mục (chip lọc), đánh dấu yêu thích (`PATCH favorite`), sắp xếp, grid/list, tìm kiếm — qua REST `/folders`, `/documents`.
- **Xem:** bấm file → client gọi `GET /documents/{id}/open` rồi stream `/download` → mở viewer phù hợp theo loại: PDF viewer / ảnh / text.
- **Thống kê:** `GET /documents/usage` → dung lượng đã dùng hiển thị ở tab Tài khoản.

### 2.3. Công cụ PDF (gộp, tách, mật khẩu, xuất Word)

- **Gộp:** tích ≥ 2 PDF → `POST /documents/merge` → pypdf nối các file → tạo tài liệu mới (bản gốc giữ nguyên).
- **Tách:** `POST /{id}/split` (vd `1-3,5`) → mỗi khoảng trang thành 1 file PDF mới.
- **Mật khẩu:** `POST /{id}/protect` (mã hóa AES) hoặc `/unprotect` (cần mật khẩu cũ) → sinh bản PDF mới.
- **Xuất Word:** "Export to Word" → service `pdf_to_docx` trích văn bản + font từ PDF, dựng layout trang → sinh file .docx tải về.

### 2.4. AI — OCR, dịch, chatbot RAG, voice

- **OCR:** `POST /ai/ocr/{document_id}` → backend đọc PDF/ảnh → gọi **Gemini** nhận diện chữ (API native, flash fallback) → trả text + độ tin cậy → hiển thị, có nút xuất DOCX. Biến thể `/word` cho từng vùng ảnh.
- **Dịch:** `POST /ai/translate` (text + cặp ngôn ngữ) → Gemini dịch → trả kết quả.
- **Chat RAG:** `POST /ai/chat` → backend trích text tài liệu được chọn làm ngữ cảnh → Gemini trả lời; hội thoại lưu DB (`/conversations`: xem, chi tiết, xóa).
- **Lệnh giọng nói:** client ghi âm → speech-to-text → `POST /ai/voice-command` → AI chọn action (chuyển tab, mở công cụ AI, đọc kết quả gần nhất…) + validate tham số → client thực thi.
- **Chụp ảnh OCR:** camera điện thoại chụp tài liệu → ảnh gửi lên endpoint OCR như trên.

### 2.5. Credit AI & thanh toán SePay

- **Số dư:** mỗi user 300 credit free/tháng (tự reset khi sang kỳ, lazy) + credit nạp; `GET /payments/credits` xem số dư.
- **Trừ/hoàn:** mỗi lượt gọi AI trừ credit (`credit_service.charge`); lượt lỗi thì tự hoàn (`refund`). Không đủ credit → lỗi 402 → UI hướng dẫn nạp.
- **Nạp credit:** chọn gói (`GET /payments/pricing`) → tạo đơn → app hiện **QR chuyển khoản SePay** (số tiền + mã đơn) → người dùng chuyển khoản → **SePay gọi webhook** `POST /payments/sepay/webhook` (xác thực API key) → cộng credit, đánh dấu đơn PAID → app thấy đơn đã thanh toán → cập nhật số dư. Lịch sử: `GET /payments/orders`.

### 2.6. Phiên bản tài liệu & so sánh

Mỗi lần sửa/tạo lại file, backend lưu snapshot vào `document_versions` (`POST /documents/{id}/versions`). Người dùng mở lịch sử phiên bản: tải về (`/download`), **phục hồi** (`/restore` — tạo phiên bản mới từ bản cũ), xóa, hoặc **so sánh 2 phiên bản** (`POST /diff` → diff theo từng đoạn văn bản, highlight thêm/bớt).

### 2.7. Chia sẻ bằng link + bình luận ghim vị trí (public)

- **Tạo link:** chủ tài liệu `POST /documents/{id}/shares` (chọn hết hoặc từng trang, hết hạn, mật khẩu tùy chọn) → sinh token ngẫu nhiên → link dạng `/shared/{token}`.
- **Người nhận (không cần tài khoản):** mở link → `GET /public/shares/{token}` (meta) → nếu có mật khẩu, nhập đúng mới được → stream file `/{token}/file` → xem trong viewer chỉ-đọc; hết hạn/sai mật khẩu/đóng link → lỗi 404/410.
- **Bình luận:** bấm vào vị trí trên trang → `POST /public/shares/{token}/comments` (page + tọa độ % + nội dung + tên khách) → chủ tài liệu xem/xóa ở màn bình luận (`GET /documents/{id}/share-comments`).
- **An toàn:** nhóm route public có rate limit theo IP, không đụng auth.

### 2.8. Biểu mẫu — gắn logo (WYSIWYG)

- **Xem mẫu:** `GET /forms/templates` (danh sách biểu mẫu sẵn trong thư mục cấu hình) → preview PDF hoặc ảnh từng trang (`/page-image` trả PNG + số trang, kích thước điểm ảnh làm nền kéo-thả).
- **Đặt logo:** kéo logo PNG/JPEG lên trang (tọa độ %) → `POST /forms/process` (multipart: logos + placements + tùy chọn watermark, mật khẩu) → backend dựng file mới (DOC→DOCX qua LibreOffice nếu cần) → chèn logo → trả file tải về.

## 3. Tóm tắt API backend (theo router)

| Nhóm | Endpoint chính | Chức năng |
|---|---|---|
| Auth | `GET/PATCH /auth/me` | Hồ sơ, đặt tên hiển thị (đăng nhập do Supabase) |
| Folders | `GET/POST /folders`, `DELETE /folders/{id}` | Danh sách / tạo / xóa thư mục |
| Documents | `GET /documents`, `GET /{id}/download`, `DELETE /{id}` | Danh sách (lọc thư mục/yêu thích), tải file, xóa |
| | `PATCH /{id}/favorite`, `POST /{id}/open`, `GET /usage` | Yêu thích, ghi nhận mở, dung lượng đã dùng |
| | `POST /merge`, `/{id}/split·protect·unprotect`, `/{id}/shares`… | Công cụ PDF, quản lý link chia sẻ + bình luận của chủ |
| Versions | `POST /documents/{id}/versions` · `/{vid}/download·restore` · `POST /diff` | Lưu/tải/phục hồi phiên bản, so sánh diff |
| AI | `POST /ai/ocr/{id}` (+`/word`), `GET /extract-text/{id}` | Nhận dạng chữ (Gemini), trích text |
| | `POST /ai/translate`, `POST /ai/chat`, `/conversations…` | Dịch, chat RAG + quản lý hội thoại |
| | `POST /ai/voice-command` | Phân tích lệnh giọng nói → action |
| Forms | `GET /forms/templates…`, `POST /forms/process` | Danh sách/preview biểu mẫu, chèn logo vào file |
| Payments | `GET /pricing·credits·orders`, `POST /sepay/webhook` | Gói credit, số dư, đơn nạp, webhook cộng credit |
| Public shares | `GET /public/shares/{token}` · `/{token}/file` · `/{token}/comments` (GET/POST) | Xem link chia sẻ, tải file, bình luận ghim (rate limit IP) |

## 4. Luồng dữ liệu điển hình (end-to-end)

- **Tải lên → OCR → chat:** chọn PDF → upload → lưu đĩa + DB → bấm OCR → Gemini → text kết quả → mở Chat, chọn tài liệu → ngữ cảnh = text đã trích → Gemini trả lời → credit trừ dần theo từng lượt.
- **Nạp credit end-to-end:** Mua credit → tạo đơn (PENDING) → QR SePay → chuyển khoản → webhook xác thực → đơn PAID + cộng credit → app cập nhật số dư → dùng tiếp tính năng AI.
- **Chia sẻ end-to-end:** menu ⋮ của file → Chia sẻ → chọn trang/hết hạn/mật khẩu → tạo link → gửi link → người nhận mở trình duyệt (không cần tài khoản) → xem + bình luận ghim → chủ file đọc và xử lý bình luận.

---

*Nguồn: đọc trực tiếp mã nguồn `backend/app/api/v1` (router.py + 8 file router), services, README.md, docs/srs-share-links.md, docs/ui-spec-files.md của repo. Sơ đồ luồng viết theo hành vi code thực tế.*
