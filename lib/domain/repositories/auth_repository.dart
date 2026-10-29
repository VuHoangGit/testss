/// Hợp đồng tầng domain cho xác thực (Supabase Auth).
library;

import '../entities/user.dart';

abstract interface class AuthRepository {
  /// Access token hiện có trong phiên (interceptor dùng gắn header).
  String? get cachedAccessToken;

  /// Phát mỗi khi phiên thay đổi: đăng nhập (kể cả popup Google), token
  /// refresh, đăng xuất ở tab khác. null = đã đăng xuất.
  Stream<AuthSession?> get sessionChanged;

  /// Phiên hiện tại (null nếu chưa đăng nhập). Profile lấy từ backend.
  Future<AuthSession?> currentSession();

  /// Đăng ký tài khoản email/mật khẩu (Supabase). Với "Confirm email" bật,
  /// đăng ký xong PHẢI xác nhận email rồi mới đăng nhập được.
  /// Trùng email → AuthException.
  Future<void> register({
    required String email,
    required String password,
    String? name,
  });

  /// Đăng nhập email/mật khẩu → phiên mới. Sai thông tin → AuthException.
  Future<AuthSession> login({required String email, required String password});

  /// Đăng nhập Google (OAuth qua Supabase). Trên web mở cửa sổ Google; khi
  /// thành công phiên về qua [sessionChanged] — method này KHÔNG trả phiên.
  Future<void> signInWithGoogle();

  /// Gửi email đặt lại mật khẩu; link trong email quay về app (redirectTo)
  /// và mở phiên recovery — app hiện màn đặt mật khẩu mới.
  Future<void> sendPasswordReset(String email);

  /// Đổi mật khẩu của phiên hiện tại (dùng cho phiên recovery).
  Future<void> updatePassword(String password);

  /// Phát `true` mỗi khi phiên đến từ link "Quên mật khẩu" (event
  /// passwordRecovery của Supabase) — AuthGate dựa vào đây để hiện màn đặt
  /// mật khẩu mới thay vì vào app chính.
  Stream<bool> get passwordRecoveryChanged;

  /// Làm mới access token (gọi khi 401). SDK tự lo refresh token bên dưới.
  Future<AuthSession> refreshSession();

  /// Đăng xuất: xóa phiên local + thu hồi refresh token phía Supabase.
  Future<void> logout();

  /// Chỉ xóa phiên local — dùng khi server ép đăng nhập lại.
  Future<void> clearLocal();
}
