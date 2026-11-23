import 'dart:async';
import 'dart:js_interop';
import 'dart:typed_data';

import 'package:web/web.dart' as web;

Future<bool> openPdfInBrowser({
  required String fileName,
  required Future<Uint8List> Function() download,
}) async {
  web.Window? tab = web.window.open('', '_blank');
  try {
    final Uint8List bytes = await download();
    if (bytes.length < 5 || bytes.sublist(0, 5).join(',') != '37,80,68,70,45') {
      tab?.close();
      throw const FormatException('Máy chủ không trả về dữ liệu PDF hợp lệ.');
    }
    final web.Blob blob = web.Blob(
      <web.BlobPart>[bytes.toJS].toJS,
      web.BlobPropertyBag(type: 'application/pdf'),
    );
    final String objectUrl = web.URL.createObjectURL(blob);
    if (tab != null) {
      tab.location.href = objectUrl;
      tab.document.title = fileName;
    } else {
      web.window.location.href = objectUrl;
    }
    unawaited(
      Future<void>.delayed(const Duration(hours: 1), () {
        web.URL.revokeObjectURL(objectUrl);
      }),
    );
    return true;
  } on Object {
    tab?.close();
    rethrow;
  }
}
