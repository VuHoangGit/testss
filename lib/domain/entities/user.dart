/// Entity người dùng + phiên đăng nhập (tầng domain — không phụ thuộc thư viện).
library;

class User {
  const User({
    required this.id,
    required this.email,
    this.name,
    this.avatarUrl,
    this.nameChosen = true,
  });

  final String id;
  final String email;
  final String? name;
  final String? avatarUrl;

  /// true = người dùng đã TỰ đặt tên hiển thị → không hỏi lại.
  /// false = lần đăng nhập đầu tiên: app hiện màn đặt tên trước khi vào app
  /// chính (Google hay email đều đi qua đây).
  ///
  /// Mặc định true để phiên dựng từ claims token (khi backend không phản hồi)
  /// và các object tạo tay không bị đẩy vào màn đặt tên.
  final bool nameChosen;
}

/// Phiên đăng nhập: access token do Supabase cấp, refresh do SDK tự lo
/// (không còn refresh token phía client app).
class AuthSession {
  const AuthSession({required this.user, required this.accessToken});

  final User user;
  final String accessToken;
}
