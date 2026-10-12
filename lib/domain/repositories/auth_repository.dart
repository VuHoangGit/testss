/// Hợp đồng tầng domain cho xác thực.
library;

import '../entities/user.dart';

abstract interface class AuthRepository {
  /// Access token hiện có trong bộ nhớ (interceptor dùng gắn header).
  String? get cachedAccessToken;

  /// Đăng nhập nhanh cho dev/demo (backend phải bật ALLOW_DEV_LOGIN).
  Future<AuthSession> devLogin({required String email, String? name});

  /// Khôi phục phiên từ secure storage lúc mở app (luồng L3). null → chưa đăng nhập.
  Future<AuthSession?> restore();

  /// Đổi refresh token lấy cặp token mới (single-flight do interceptor lo).
  Future<AuthSession> refreshSession();

  /// Đăng xuất: revoke server (best-effort) rồi xóa token local (EC-18..21).
  Future<void> logout();

  /// Chỉ xóa token local — dùng khi server ép đăng nhập lại (EC-17).
  Future<void> clearLocal();
}
