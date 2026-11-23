/// Test VM không có localStorage/file user: giữ tên trong bộ nhớ phiên test.
library;

String? _savedName;

String readGuestName() => _savedName ?? '';

void writeGuestName(String name) {
  _savedName = name.trim();
}
