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

class AuthSession {
  const AuthSession({
    required this.user,
    required this.accessToken,
    required this.refreshToken,
  });

  final User user;
  final String accessToken;
  final String refreshToken;
}
