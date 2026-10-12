/// FileSaver cho web: kích hoạt tải xuống bằng thẻ <a download> ẩn
/// (dùng package:web — bản wrapper kiểu an toàn của các DOM API).
library;

import 'dart:js_interop';
import 'dart:typed_data';

import 'package:web/web.dart' as web;

class FileSaver {
  const FileSaver();

  /// Tạo Blob từ bytes và click thẻ <a download> → trình duyệt tải file về.
  /// Trả về tên file (web không có đường đĩa), null không xảy ra.
  Future<String?> saveBytes({
    required String fileName,
    required Uint8List bytes,
    String mimeType = 'application/octet-stream',
  }) async {
    final web.Blob blob = web.Blob(
      <web.BlobPart>[bytes.toJS].toJS,
      web.BlobPropertyBag(type: mimeType),
    );
    final web.HTMLAnchorElement anchor = web.HTMLAnchorElement()
      ..href = web.URL.createObjectURL(blob)
      ..download = fileName;
    web.document.body!.appendChild(anchor);
    anchor.click();
    anchor.remove();
    web.URL.revokeObjectURL(anchor.href);
    return fileName;
  }
}
