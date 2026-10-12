/// Failure tầng domain — presentation chỉ làm việc với các kiểu này.
library;

sealed class Failure {
  const Failure(this.message);

  final String message;

  @override
  String toString() => message;
}

/// Sai/hết hạn phiên, token Google không hợp lệ → hiển thị màn đăng nhập.
class AuthFailure extends Failure {
  const AuthFailure(super.message);
}

/// Mất kết nối / backend chết → giữ nguyên phiên, hiện màn thử lại (EC-16).
class NetworkFailure extends Failure {
  const NetworkFailure(super.message);
}

/// Lỗi không lường trước — log lại, hiển thị thông báo chung.
class UnexpectedFailure extends Failure {
  const UnexpectedFailure(super.message);
}
