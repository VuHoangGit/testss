/// Exception tầng data — repository map thành Failure cho presentation.
library;

/// Lỗi xác thực (token sai/hết hạn/bị thu hồi) → dẫn tới đăng nhập lại.
class AuthException implements Exception {
  const AuthException(this.message);

  final String message;

  @override
  String toString() => message;
}

/// Lỗi hạ tầng: mất mạng / timeout / 5xx — KHÔNG được dẫn tới logout (EC-16).
class NetworkException implements Exception {
  const NetworkException([this.message = 'Không thể kết nối máy chủ']);

  final String message;

  @override
  String toString() => message;
}
