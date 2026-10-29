---
name: project-testss-doc-app
description: Bối cảnh dự án testss — Doc App (Flutter web + FastAPI), auth đang chuyển từ JWT tự issue sang Supabase Auth + Google provider (backend verify JWKS); các quyết định mở
metadata:
  type: project
---

Dự án `C:\Users\hoang\Downloads\testss` — "DocuVault": app quản lý tài liệu (upload PDF/ảnh, OCR, dịch, chat AI, voice command). Flutter web (localhost:53123) + backend FastAPI (localhost:8000, port prefix /api/v1). Nguồn requirement gốc là danh sách 6 sprint của khách (không có SRS); docs/analysis-sprint1.md là phân tích Sprint 1 do caller ghi.

**Tình trạng auth (kiểm chứng 2026-10-26):**
- Backend đã hiện thực đầy đủ: /auth/login + /auth/register (email/password, PBKDF2), /auth/google (verify Google id_token), /auth/dev, /auth/refresh (rotation, hash SHA-256 trong bảng user_sessions), /auth/logout, /auth/me. JWT HS256 tự ký (JWT_SECRET, iss=docuvault, claims sub+sid+email/name/picture). deps.get_current_session_and_user check session revoked trong DB mỗi request.
- Flutter: login email/password chạy thật; nút "Continue with Google" chỉ hiện SnackBar (chưa có client ID). google_sign_in có trong pubspec nhưng KHÔNG import ở đâu (gỡ được không đụng code). DesktopGoogleSignIn (loopback+PKCE cho Windows) viết sẵn, DEFERRED, không wire UI.

**Quyết định đã chốt bởi user (2026-10-26): thay toàn bộ auth bằng Supabase Auth**
- Đăng nhập Google qua Google provider của Supabase. Backend FastAPI giữ nguyên, chỉ đổi verify: JWT tự issue → verify Supabase JWT bằng JWKS.
- User đã tạo project Supabase + kết nối GitHub Integration (repo VuHoangGit/testss, branch main).
- Chưa có Google OAuth Client ID/Secret — LƯU Ý: Google provider của Supabase VẪN yêu cầu tự tạo Web OAuth Client trên Google Cloud Console (redirect URI = https://<ref>.supabase.co/auth/v1/callback) rồi nhập vào dashboard Supabase; chỉ là không cần client ID từng nền tảng nhúng trong app nữa.

**Why:** user muốn bỏ gánh nặng tự quản JWT/refresh/session; Google login chưa từng chạy thật nên không có torniquet khi thay.

**How to apply:** mọi phân tích task auth sau này lấy quyết định Supabase làm gốc; các câu hỏi mở còn lại xem báo cáo phân tích ngày 2026-10-26 (đã trả caller): (1) giữ email/password song song qua Supabase hay chỉ Google; (2) migrate dữ liệu user SQLite hay chỉ dữ liệu test; (3) dùng Supabase PostgreSQL làm DB chính luôn không; (4) logout cần revoke tức thì (Admin API) hay chấp nhận token hết hạn tự chết; (5) redirect URLs + CORS cho localhost:53123; (6) chiến lược test backend với JWKS.
