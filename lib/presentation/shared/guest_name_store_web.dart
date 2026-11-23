/// Lưu tên khách bình luận trên localStorage (SRS FR-4.3).
library;

import 'package:web/web.dart' as web;

const String _kStorageKey = 'docuvault.share.guestName';

String readGuestName() {
  try {
    return web.window.localStorage.getItem(_kStorageKey) ?? '';
  } catch (_) {
    return ''; // Trình duyệt chặn storage: vẫn cho nhập tên trong phiên này.
  }
}

void writeGuestName(String name) {
  try {
    web.window.localStorage.setItem(_kStorageKey, name.trim());
  } catch (_) {
    // Không chặn gửi bình luận nếu storage không khả dụng.
  }
}
