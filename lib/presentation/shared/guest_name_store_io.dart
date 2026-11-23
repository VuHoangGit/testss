/// Desktop/mobile: lưu tên khách cục bộ trong thư mục dữ liệu của app.
/// Không thêm package path_provider; lỗi ghi không được chặn bình luận.
library;

import 'dart:io';

const String _kFileName = 'docuvault-guest-name.txt';

File _storeFile() {
  final String base = Platform.isWindows
      ? Platform.environment['APPDATA'] ?? Directory.systemTemp.path
      : Platform.environment['HOME'] ?? Directory.systemTemp.path;
  return File('$base${Platform.pathSeparator}DocuVault${Platform.pathSeparator}$_kFileName');
}

String readGuestName() {
  try {
    return _storeFile().readAsStringSync().trim();
  } on FileSystemException {
    return '';
  }
}

void writeGuestName(String name) {
  try {
    final File file = _storeFile();
    file.parent.createSync(recursive: true);
    file.writeAsStringSync(name.trim());
  } on FileSystemException {
    // Không chặn gửi bình luận nếu bộ nhớ máy không khả dụng.
  }
}
