/// Bản nền không phải web (VM/test) — không có localStorage, no-op.
///
/// Vì thế ô "địa chỉ máy chủ" chỉ hiển thị và có tác dụng trên web.
library;

String? readServerUrlOverride() => null;

void writeServerUrlOverride(String? value) {}

/// Nền không web không thể reload trang → trả false để UI hiện hướng dẫn.
bool reloadApp() => false;
