/// Exception tầng data — controller bắt và hiển thị message cho người dùng.
library;

/// Lỗi xác thực (token sai/hết hạn/bị thu hồi) → dẫn tới đăng nhập lại.
class AuthException implements Exception {
  const AuthException(this.message, {this.needsEmailConfirmation = false});

  final String message;

  /// true: tài khoản ĐÃ tạo nhưng Supabase chờ bấm link xác nhận trong hộp
  /// thư — UI hiện hướng dẫn thay vì báo lỗi đỏ.
  final bool needsEmailConfirmation;

  @override
  String toString() => message;
}

/// Lỗi hạ tầng: mất mạng / timeout / 5xx — KHÔNG được dẫn tới logout (EC-16).
class NetworkException implements Exception {
  const NetworkException([this.message = 'Could not connect to the server']);

  final String message;

  @override
  String toString() => message;
}

/// Hết credit (HTTP 402) — UI hiện hướng dẫn nạp thêm, không phải lỗi hệ thống.
class InsufficientCreditsException implements Exception {
  const InsufficientCreditsException(this.message);

  final String message;

  @override
  String toString() => message;
}
