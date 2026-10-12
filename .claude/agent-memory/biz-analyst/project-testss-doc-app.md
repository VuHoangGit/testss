---
name: project-testss-doc-app
description: Bối cảnh dự án testss — app quản lý tài liệu đa nền tảng (Flutter + backend chưa chốt + PostgreSQL), 6 sprint, Sprint 1 = infra + Google auth; các quyết định đang chờ user chốt
metadata:
  type: project
---

Dự án thư mục `C:\Users\hoang\Downloads\testss`: app quản lý tài liệu đa nền tảng — Flutter client (Android/iOS/Windows/macOS) + Backend (FastAPI hoặc Node.js, CHƯA chốt) + PostgreSQL + AI (OCR/chatbot ở sprint 3-6).

**Nguồn requirement duy nhất là danh sách 6 sprint khách đưa — KHÔNG có SRS/technical design trong repo.** Repo đã kiểm chứng (2026-10-12): Flutter template mặc định, chỉ scaffold android/ios/windows, KHÔNG có macos/.

Sprint: 1 = khởi tạo + schema users/sessions + Google OAuth2 server-side + JWT + Flutter Clean Architecture + Login + Shell. 2 = kho tài liệu/S3/PDF. 3 = OCR. 4 = table extractor/auto-tag/redaction. 5 = PDF diff. 6 = RAG chatbot (pgvector).

Phát hiện quan trọng: sprint 1 ghi "google_sign_in cho Desktop" nhưng package này KHÔNG hỗ trợ Windows/Linux; repo desktop = Windows → phải chọn phương án (a) flutter_appauth PKCE, (b) loopback + oauth2, (c) defer.

**Why:** mọi phân tích nghiệp vụ sau này (Sprint 2+) đều phải quy về danh sách sprint này vì không có nguồn nào khác; các gap đều phải đánh dấu ❓ hỏi user, không bịa.

**How to apply:** trước khi phân tích sprint tiếp theo, đọc lại danh sách sprint trong ngữ cảnh task; các quyết định đã chốt bởi user cần được cập nhật vào memory này. Đến 2026-10-12 còn 7 quyết định chờ chốt: (1) backend FastAPI vs Node.js; (2) PostgreSQL Docker vs native; (3) phương án Windows login; (4) thời hạn JWT access/refresh + rotation; (5) tên app/branding/ngôn ngữ UI; (6) giới hạn domain/whitelist đăng nhập; (7) giới hạn số session/user. Bản phân tích đầy đủ Sprint 1 đã trả về caller dạng text (guard chặn subagent ghi file) — caller phụ trách ghi `docs/analysis-sprint1.md`.
