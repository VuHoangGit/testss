/// Bản nền web — đọc/ghi localStorage của trình duyệt.
library;

import 'package:web/web.dart' as web;

const String _kStorageKey = 'docuvault.theme';

String? readSavedTheme() {
  try {
    return web.window.localStorage.getItem(_kStorageKey);
  } catch (_) {
    return null; // trình duyệt chặn localStorage → dùng mặc định system
  }
}

void writeSavedTheme(String value) {
  try {
    web.window.localStorage.setItem(_kStorageKey, value);
  } catch (_) {
    // Bỏ qua: không lưu được thì vẫn đổi theme trong phiên hiện tại.
  }
}
