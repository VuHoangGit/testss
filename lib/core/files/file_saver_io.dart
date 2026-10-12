/// FileSaver cho desktop/mobile: dialog "Lưu as" của hệ điều hành.
/// file_picker 13 tự ghi bytes vào nơi người dùng chọn và trả về Uri.
library;

import 'dart:typed_data';

import 'package:file_picker/file_picker.dart';

class FileSaver {
  const FileSaver();

  /// Mở dialog chọn nơi lưu; plugin ghi bytes xuống đĩa. Trả về đường dẫn
  /// đã lưu, null nếu người dùng hủy.
  Future<String?> saveBytes({
    required String fileName,
    required Uint8List bytes,
    String mimeType = 'application/octet-stream',
  }) async {
    final Uri? uri = await FilePicker.saveFile(
      fileName: fileName,
      bytes: bytes,
      mimeType: mimeType,
    );
    if (uri == null) return null; // người dùng hủy
    return uri.scheme == 'file' ? uri.toFilePath() : uri.toString();
  }
}
