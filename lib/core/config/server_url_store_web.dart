/// Bản nền web — đọc/ghi localStorage của trình duyệt.
library;

import 'package:web/web.dart' as web;

const String _kStorageKey = 'docuvault.serverUrl';

String? readServerUrlOverride() {
  try {
    final String? value = web.window.localStorage.getItem(_kStorageKey);
    return (value == null || value.isEmpty) ? null : value;
  } catch (_) {
    return null; // trình duyệt chặn localStorage → dùng mặc định build-time
  }
}

void writeServerUrlOverride(String? value) {
  try {
    if (value == null || value.isEmpty) {
      web.window.localStorage.removeItem(_kStorageKey);
    } else {
      web.window.localStorage.setItem(_kStorageKey, value);
    }
  } catch (_) {
    // Bỏ qua: không lưu được thì lần mở sau vẫn dùng mặc định build-time.
  }
}

/// Tải lại trang để Dio/provider dựng lại với địa chỉ mới (providers giữ Dio
/// suốt phiên, không tự đọc lại override). Trả false khi trình duyệt chặn.
bool reloadApp() {
  try {
    web.window.location.reload();
    return true;
  } catch (_) {
    return false;
  }
}
