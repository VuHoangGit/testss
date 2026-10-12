/// HTTP server tạm trên `127.0.0.1:{port động}` nhận redirect từ Google
/// sau khi user đăng nhập trên trình duyệt hệ thống (pattern loopback RFC 8252).
library;

import 'dart:async';
import 'dart:convert';
import 'dart:io';

import '../error/exceptions.dart';

class LoopbackOAuthServer {
  HttpServer? _server;

  bool get isRunning => _server != null;

  int get port {
    final HttpServer? server = _server;
    if (server == null) {
      throw StateError('Server chưa start');
    }
    return server.port;
  }

  Future<void> start() async {
    assert(_server == null, 'Server đang chạy');
    // Port 0 = OS cấp port động rảnh → tránh đụng port bị chiếm (EC-23)
    _server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
  }

  /// Đợi Google redirect về kèm `code`.
  ///
  /// - Sai state → StateError (tránh CSRF).
  /// - Google trả error → [AuthException].
  /// - Không có request nào trong [timeout] → [AuthException] hết thời gian (EC-24).
  Future<String> waitForCode({
    required String expectedState,
    Duration timeout = const Duration(minutes: 10),
  }) async {
    final HttpServer? server = _server;
    if (server == null) {
      throw StateError('Server chưa start');
    }
    try {
      // Lưu ý: timeout của Stream.timeout là khoảng trống GIỮA 2 event — với
      // luồng đăng nhập, không có event trong 10 phút ≈ user bỏ dở flow.
      await for (final HttpRequest request in server.timeout(timeout)) {
        final Uri uri = request.uri;
        final String? code = uri.queryParameters['code'];
        final String? error = uri.queryParameters['error'];
        final String? state = uri.queryParameters['state'];

        // Request phụ (favicon...) không phải redirect của Google → bỏ qua
        if (code == null && error == null) {
          await request.response.close();
          continue;
        }

        if (error != null) {
          await _respondAndClose(request, 'Đăng nhập không thành công: $error');
          throw AuthException('Google trả về lỗi: $error');
        }
        if (state != expectedState || code == null) {
          await _respondAndClose(request, 'Yêu cầu không hợp lệ (state không khớp).');
          throw StateError('State không khớp hoặc thiếu code');
        }
        await _respondAndClose(
          request,
          'Đăng nhập thành công! Hãy đóng trang này và quay lại ứng dụng DocuVault.',
        );
        return code;
      }
      throw StateError('Server đã đóng trước khi nhận được phản hồi');
    } on TimeoutException {
      throw const AuthException('Đã quá thời gian đăng nhập, vui lòng thử lại');
    } finally {
      await stop();
    }
  }

  Future<void> _respondAndClose(HttpRequest request, String message) async {
    final String safe = const HtmlEscape().convert(message);
    request.response.headers.contentType = ContentType.html;
    request.response.write(
      '<html><body style="font-family:sans-serif;text-align:center;padding-top:48px">'
      '<h2>$safe</h2></body></html>',
    );
    await request.response.close();
  }

  Future<void> stop() async {
    final HttpServer? server = _server;
    _server = null;
    await server?.close(force: true);
  }
}
