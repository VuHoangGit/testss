/// Entity người dùng + phiên đăng nhập (tầng domain — không phụ thuộc thư viện).
library;

class User {
  const User({
    required this.id,
    required this.email,
    this.name,
    this.avatarUrl,
  });

  final String id;
  final String email;
  final String? name;
  final String? avatarUrl;
}

/// Phiên đăng nhập: access token do Supabase cấp, refresh do SDK tự lo
/// (không còn refresh token phía client app).
class AuthSession {
  const AuthSession({required this.user, required this.accessToken});

  final User user;
  final String accessToken;
}
