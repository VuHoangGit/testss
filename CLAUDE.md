# CLAUDE.md — Doc App (Flutter + FastAPI)

## Kiểm thử UI bằng Playwright (tự động)

- `.mcp.json` đã cấu hình Playwright MCP. Khi task liên quan đến UI web (`lib/presentation/**`, `web/`) hoặc khi repo/hệ thống đã có test cần chạy kiểm thử, **tự bật Playwright MCP để test, không cần hỏi lại**.
- Luôn mở trình duyệt **headed** (có cửa sổ nhìn được), KHÔNG dùng headless.
- Trình tự mặc định:
  1. Đảm bảo app chạy được (backend `uvicorn`, frontend `flutter run -d chrome` hoặc URL dev đang mở).
  2. `browser_navigate` tới URL app → chờ trang tải xong (`browser_snapshot`).
  3. Tương tác theo kịch bản test (click/fill bằng ref từ snapshot, không guessed selector).
  4. `browser_take_screenshot` làm bằng chứng, báo kèm console error nếu có.
- Nếu app chưa chạy mà cần test: khởi động app ở background trước, rồi mới điều hướng.
