# SRS — Chia sẻ tài liệu bằng link + Bình luận ghim vị trí

Trạng thái: **Đã chốt** · Phạm vi: backend FastAPI + Flutter (web/desktop/mobile)
Chia 2 pha giao hàng: **P1 — link chia sẻ chỉ xem** (bắt buộc), **P2 — bình luận ghim vị trí** (độc lập, làm sau).

---

## 1. Mục tiêu & bối cảnh

Cho phép chủ tài liệu tạo **link công khai có token** để người khác xem tài liệu **không cần tài
khoản**. P2: người nhận bình luận, comment được **ghim tại trang + tọa độ** trên PDF, hiển thị
thread kiểu Google Docs.

### Quyết định kiến trúc quan trọng (không hỏi lại)

1. **KHÔNG dùng bảng `permissions` hiện có cho tính năng này.** Bảng đó là `(document_id,
   user_id NOT NULL, role)` — thiết kế cho chia sẻ giữa **người dùng có tài khoản**. Người nhận
   link không có user_id. Tính năng này dùng bảng mới `document_shares` (token-based). Bảng
   `permissions` giữ nguyên, dùng cho tương lai (share cho user có tài khoản).
2. **Token lưu dạng SHA-256 hash**, không lưu raw. Raw token chỉ xuất hiện 1 lần trong URL khi
   tạo link. Tra cứu bằng `token_hash` (unique index). Token = `secrets.token_urlsafe(24)`
   (~192 bit entropy, không thể dò brute-force qua HTTP).
3. **Route public tách biệt tuyệt đối** với route đã đăng nhập: prefix `/api/v1/public/...`,
   **không dùng dependency `CurrentUser`**, client **không bao giờ gửi document_id** — chỉ gửi
   token. Mọi thao tác đều suy document từ token hash.
4. **Tài liệu không thêm thư viện mới.** Flutter dùng tiếp syncfusion_flutter_pdfviewer
   (viewer có sẵn) + overlay `Stack` tự viết cho pin. Không thêm go_router — deep link qua
   query param `?share=TOKEN` (app đang dùng Navigator mệnh lệnh + `navigatorKey`).

---

## 2. Yêu cầu chức năng — P1: Link chia sẻ chỉ xem

### FR-1 Quản lý link (chủ tài liệu, đã đăng nhập)

| ID | Yêu cầu |
|---|---|
| FR-1.1 | Menu ⋮ của tài liệu có mục **"Chia sẻ…"** → mở Share dialog. |
| FR-1.2 | Tạo link: chọn **quyền** (`Chỉ xem` — P1 chỉ có lựa chọn này; `Bình luận` hiện nhưng khóa kèm nhãn "sắp có"), chọn **thời hạn**: 1 ngày / 7 ngày / 30 ngày / Không hết hạn. Nút "Tạo link". |
| FR-1.3 | Sau khi tạo: hiện URL đầy đủ + nút **Sao chép** (clipboard + toast "Đã sao chép"). URL dạng `{app_base}/?share={token}`. |
| FR-1.4 | Dialog liệt kê **mọi link của tài liệu**: quyền, ngày tạo, ngày hết hạn (hoặc "vô hạn"), trạng thái (Đang hoạt động / Đã hết hạn / Đã thu hồi), số lượt xem, nút **Thu hồi** từng link. |
| FR-1.5 | Thu hồi = đặt `is_active = false`. Link đã thu hồi trả 404 như link không tồn tại. Không có "bỏ thu hồi". |
| FR-1.6 | Tối đa **10 link đang hoạt động** / tài liệu. Vượt → lỗi 400 "Đã đạt giới hạn 10 link đang hoạt động". |
| FR-1.7 | Chỉ `Document.owner_id` được tạo/thu hồi/xem danh sách link. Người khác → 404 (không 403, tránh lộ sự tồn tại). |
| FR-1.8 | Link luôn phục vụ **bản hiện tại** của tài liệu (restore version / upload bản mới thì người nhận thấy bản mới ngay). |

### FR-2 Truy cập của người nhận (public, không đăng nhập)

| ID | Yêu cầu |
|---|---|
| FR-2.1 | `GET /api/v1/public/shares/{token}` → metadata: `file_name`, `mime_type`, `size_bytes`, `page_count` (nếu PDF), `permission`, `expires_at`, `owner_name`. **Không trả** `document_id`, `storage_key`, hay bất kỳ id nội bộ nào. |
| FR-2.2 | `GET /api/v1/public/shares/{token}/file` → stream file. PDF: `Content-Disposition: inline; filename="..."` (tên đã sanitize — dùng lại pattern `_attachment_header` trong `documents.py`, biến thể inline). MIME khác PDF → `attachment` (tải xuống, không render). |
| FR-2.3 | Token sai / đã thu hồi / đã hết hạn → **404 với message chung chung**: `"Link không tồn tại hoặc đã hết hạn"`. Không phân biệt 3 trường hợp (chống dò). |
| FR-2.4 | Hết hạn tính theo **giờ server** lúc nhận request (không cần cron dọn). |
| FR-2.5 | Mỗi lần GET file thành công → tăng `view_count` (best-effort, không chặn response). |
| FR-2.6 | Rate limit theo **IP** (không phải theo user — người nhận không có user): metadata 60/phút/IP, file 30/phút/IP. Dùng cùng cơ chế limiter trong `deps.py`, thêm biến đếm theo IP. |
| FR-2.7 | Phạm vi chia sẻ: **mọi loại tài liệu app đang xem được** (PDF, ảnh, text) — màn share tái dùng logic chọn viewer của `viewer_opener.dart`. |

### FR-3 UI người nhận

| ID | Yêu cầu |
|---|---|
| FR-3.1 | Mở `?share=TOKEN` (kể cả khi app đã đăng nhập dưới tài khoản khác) → điều hướng thẳng **SharedView**, bỏ qua login. |
| FR-3.2 | SharedView: banner trên cùng "Tài liệu được chia sẻ bởi {owner_name}" + tên file; thân là viewer **chỉ đọc** — ẩn mọi nút công cụ (tải lên, ⋮ menu, tools), chỉ còn điều hướng trang + zoom. |
| FR-3.3 | Link chết → màn lỗi thân thiện tiếng Việt + nút "Về trang chủ". |
| FR-3.4 | File PDF đã có mật khẩu (tạo bởi tool "Đặt mật khẩu"): viewer sẽ tự hỏi mật khẩu — ghi chú trong dialog chia sẻ "File này có mật khẩu, người nhận cần biết mật khẩu để mở". |
| FR-3.5 | Metadata lỗi/timeout → thông báo "Không tải được tài liệu" + nút thử lại. |

---

## 3. Yêu cầu chức năng — P2: Bình luận ghim vị trí

### FR-4 Mô hình bình luận

| ID | Yêu cầu |
|---|---|
| FR-4.1 | Comment thuộc về **một share link** (không phải document): người nhận vào bằng link nào thì thấy/thêm comment của link đó. |
| FR-4.2 | Vị trí: `page_number` (1-based) + `norm_x`, `norm_y` ∈ [0,1] — **tọa độ chuẩn hóa theo kích thước trang PDF** (user-space), độc lập với zoom và kích thước màn hình. |
| FR-4.3 | Nội dung: 1–2000 ký tự. Tên tác giả: người nhận tự nhập lần đầu, lưu `localStorage`, giới hạn 80 ký tự; bỏ trống → "Khách". Không có tài khoản, không xác thực danh tính. |
| FR-4.4 | Reply 1 cấp (`parent_id` → comment gốc); không lồng sâu hơn. |
| FR-4.5 | **Chỉ link `permission=comment` mới được POST**; link `view` → 403 "Link này chỉ cho phép xem". |
| FR-4.6 | Tối đa **500 comment / share**; vượt → 400 "Chủ đề đã đầy". |
| FR-4.7 | Ai được sửa/xóa: **không ai được sửa**; **chủ tài liệu xóa được comment bất kỳ**; người nhận không xóa được (v1 — giữ đơn giản, ghi rõ trong UI). |
| FR-4.8 | Ghim vị trí **chỉ hỗ trợ PDF**. Tài liệu ảnh/text: comment không ghim (thread chung). |

### FR-5 API bình luận (public, theo token)

| Endpoint | Mô tả |
|---|---|
| `GET /public/shares/{token}/comments` | List đầy đủ, sort `(page_number, created_at)`. Kèm cả comment đã bị xóa? — Không, xóa là xóa hẳn. |
| `POST /public/shares/{token}/comments` | Body: `{page_number, norm_x, norm_y, author_name, body, parent_id?}`. Rate limit 10/phút/IP. |
| `DELETE /public/shares/{token}/comments/{id}` | **Chỉ chủ tài liệu** — endpoint này nằm ở nhóm đã đăng nhập: `DELETE /documents/{document_id}/share-comments/{id}` (dùng `CurrentUser`, suy comment thuộc về share của document đó). |

### FR-6 UI bình luận

| ID | Yêu cầu |
|---|---|
| FR-6.1 | SharedView thêm **sidebar phải** (collapsible, mặc định mở khi có comment): thread kiểu Google Docs — mỗi comment: avatar chữ cái đầu tên, tên, thời gian tương đối ("5 phút trước"), nội dung, dòng nhỏ "trang {n}". |
| FR-6.2 | **Pin overlay**: chấm tròn đánh số trên trang PDF tại đúng `(norm_x, norm_y)`; bấm pin → scroll sidebar tới comment + highlight; bấm comment trong sidebar → viewer nhảy tới trang + nhấp nháy pin. |
| FR-6.3 | Pin phải **đứng yên tại đúng điểm nội dung** khi zoom / pan / lật trang (chỉ vẽ pin của trang đang hiển thị). Cách tính: offset trang hiện hành + `norm × kích thước trang × zoomLevel` − scroll offset. |
| FR-6.4 | Thêm comment: chế độ "ghim" (nút 📌 bật/tắt) → chạm vào PDF tại đâu thì lấy tọa độ tại đó mở hộp nhập; hoặc nút "Bình luận" trong sidebar (không ghim, `page_number` = trang hiện tại, tọa độ giữa trang). |
| FR-6.5 | Chủ tài liệu xem comment ở **app chính**: menu ⋮ → "Bình luận chia sẻ ({số})" → mở cùng màn SharedView (dùng link đầu tiên còn hoạt động) với quyền xóa từng comment. |
| FR-6.6 | Polling nhẹ: SharedView refetch comments mỗi 30s khi tab đang mở (không cần WebSocket). |

---

## 4. Mô hình dữ liệu

```sql
-- Bảng mới 1 (P1)
document_shares (
  id           UUID PRIMARY KEY,
  document_id  UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  token_hash   CHAR(64) NOT NULL UNIQUE,      -- sha256 hex của token
  permission   VARCHAR(10) NOT NULL DEFAULT 'view',   -- 'view' | 'comment'
  expires_at   TIMESTAMPTZ NULL,              -- NULL = không hết hạn
  is_active    BOOLEAN NOT NULL DEFAULT TRUE,
  view_count   INT NOT NULL DEFAULT 0,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_shares_document ON document_shares(document_id);

-- Bảng mới 2 (P2)
share_comments (
  id           UUID PRIMARY KEY,
  share_id     UUID NOT NULL REFERENCES document_shares(id) ON DELETE CASCADE,
  parent_id    UUID NULL REFERENCES share_comments(id) ON DELETE CASCADE,
  page_number  INT NOT NULL,
  norm_x       FLOAT NOT NULL,
  norm_y       FLOAT NOT NULL,
  author_name  VARCHAR(80) NOT NULL DEFAULT 'Khách',
  body         TEXT NOT NULL,                 -- 1..2000 ký tự, kiểm tra ở schema
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

- Migration: script idempotent `backend/scripts/migrate_add_shares.py` theo đúng pattern các
  script hiện có (`create_all` + chỉ tạo những gì thiếu).
- Model SQLAlchemy: `app/models/document_share.py`, `app/models/share_comment.py`; đăng ký
  `app/models/__init__.py`.
- **Không sửa** bảng `permissions`.

## 5. API spec đầy đủ

### Nhóm chủ tài liệu (yêu cầu `CurrentUser`, prefix `/api/v1/documents`)

| Method + path | Body → Response |
|---|---|
| `POST /documents/{id}/shares` | `{permission: "view"|"comment", expires_in_hours: int\|null}` → `ShareOut {id, permission, expires_at, is_active, view_count, share_url, created_at}` — `share_url` ghép từ setting `PUBLIC_WEB_BASE_URL` (mặc định `http://localhost:53123`) |
| `GET /documents/{id}/shares` | → `ShareOut[]` (gồm cả link đã thu hồi/hết hạn, kèm `share_url` nếu còn active) |
| `DELETE /documents/{id}/shares/{share_id}` | → 204. Sai share_id / không phải owner → 404 |
| `GET /documents/{id}/share-comments` | (P2) mọi comment của mọi share của document, kèm `share_id` |
| `DELETE /documents/{id}/share-comments/{comment_id}` | (P2) → 204 |

### Nhóm public (KHÔNG auth, prefix `/api/v1/public`, rate limit theo IP)

| Method + path | Response |
|---|---|
| `GET /public/shares/{token}` | `{file_name, mime_type, size_bytes, page_count?, permission, expires_at, owner_name}` · 404 chung chung nếu sai/hết hạn/thu hồi |
| `GET /public/shares/{token}/file` | Stream file (PDF inline, còn lại attachment) · tăng view_count |
| `GET /public/shares/{token}/comments` | (P2) `CommentOut[]` |
| `POST /public/shares/{token}/comments` | (P2) `CommentOut` · 403 nếu permission=view |

Đăng ký router mới `app/api/v1/public_shares.py` vào `router.py` (tách file, không nhét vào
`documents.py` — giữ ranh giới "public" nhìn thấy được bằng mắt).

## 6. Flow client chính

1. **Tạo:** ⋮ → "Chia sẻ…" → chọn thời hạn → "Tạo link" → POST → hiện URL + copy.
2. **Người nhận mở link:** app đọc `Uri.base.queryParameters['share']` ngay trong `main()`
   trước khi quyết định màn đầu → push `SharedView(token)`; providers gọi public API
   (Dio instance riêng **không gắn** interceptor Supabase auth).
3. **Tải file trong SharedView:** GET file → bytes → viewer theo mime (tái dùng
   `viewer_opener.dart` logic chọn PDF/image/text viewer, biến thể read-only).
4. **P2 ghim:** bật chế độ 📌 → `GestureDetector` bắt tap lên vùng viewer → quy đổi tọa độ
   màn hình → tọa độ chuẩn hóa (chia cho kích thước hiển thị của trang đó) → hộp nhập → POST.

## 7. Yêu cầu phi chức năng

- **Bảo mật:** token 192-bit + lưu hash; 404 không phân biệt nguyên nhân; không trả id nội bộ
  ở public API; filename trong Content-Disposition phải sanitize (không `\r\n`); response kèm
  `X-Content-Type-Options: nosniff`; log chỉ in 8 ký tự đầu token để truy vết mà không lộ.
- **Hiệu năng:** GET file **stream** (`FileResponse`/chunked), không đọc cả file vào RAM
  (file lớn hiện vẫn `read_document_bytes` — endpoint public phải làm đúng hơn).
- **Không tính credit:** chia sẻ + bình luận không phải tính năng AI, không trừ credit, không
  đụng bảng credit. Bytes tính quota của **owner**.
- **Ngôn ngữ:** toàn bộ message UI + lỗi backend tiếng Việt, đúng convention repo.

## 8. Test bắt buộc

Backend (`tests/test_shares.py` — P1, `test_share_comments.py` — P2):

1. Tạo link → GET metadata đúng thông tin, KHÔNG có document_id trong response.
2. GET file thành công, header inline cho PDF, attachment cho ảnh.
3. Token sai / thu hồi / hết hạn (fake thời gian) → 404 cùng message.
4. Không phải owner tạo link → 404. Owner mới (user khác) không thấy link của document người khác.
5. Xóa document → link chết ngay (404), dòng DB bị cascade.
6. Rate limit IP: vượt ngưỡng → 429.
7. Quá 10 link active → 400.
8. (P2) POST comment qua link view → 403; qua link comment → 201, sort đúng; owner xóa được, guest không; quá 500 → 400; reply đúng 1 cấp.

Flutter (`test/widget/share_flow_test.dart`):

1. Share dialog: tạo link giả (repo fake) → hiện URL + copy callback được gọi.
2. SharedView với token hợp lệ: hiện tên file + banner owner, không có nút công cụ.
3. Token 404 → màn lỗi.
4. (P2) render list comment + pin tại vị trí quy đổi (widget test tính tọa độ).

## 9. Tiêu chí nghiệm thu tay

**P1:** tạo dự án → upload PDF → chia sẻ 7 ngày → mở link ở trình duyệt ẩn danh (không đăng
nhập) → xem được PDF đầy đủ, zoom/lật trang → thu hồi → refresh → 404. Xóa tài liệu → link chết.

**P2:** mở link ở 2 trình duyệt khác nhau (2 "khách") → A ghim comment trang 3 góc phải trên →
B thấy pin đúng chỗ + reply → chủ tài liệu vào "Bình luận chia sẻ" → xóa comment của A → cả 2 bên mất.

## 10. Ngoài phạm vi (ghi rõ để không phình)

- Link có mật khẩu riêng (P3 nếu cần).
- Chia sẻ cho **tài khoản cụ thể** với quyền edit (dùng bảng `permissions` — tương lai).
- Realtime (WebSocket/SSE) — polling đủ dùng.
- Chỉnh sửa comment, đính kèm file trong comment.
- Thống kê xem chi tiết (ai xem, khi nào) — chỉ có `view_count` tổng.
