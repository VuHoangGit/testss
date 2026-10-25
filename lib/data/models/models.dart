/// Model tầng data: parse JSON từ backend → entity domain.
library;

import '../../domain/entities/user.dart';

class UserModel {
  const UserModel({
    required this.id,
    required this.email,
    this.name,
    this.avatarUrl,
  });

  factory UserModel.fromJson(Map<String, dynamic> json) => UserModel(
    id: json['id'] as String,
    email: json['email'] as String,
    name: json['name'] as String?,
    avatarUrl: json['avatar_url'] as String?,
  );

  final String id;
  final String email;
  final String? name;
  final String? avatarUrl;

  User toEntity() =>
      User(id: id, email: email, name: name, avatarUrl: avatarUrl);
}

class TokenResponseModel {
  const TokenResponseModel({
    required this.accessToken,
    required this.refreshToken,
    required this.user,
  });

  factory TokenResponseModel.fromJson(Map<String, dynamic> json) =>
      TokenResponseModel(
        accessToken: json['access_token'] as String,
        refreshToken: json['refresh_token'] as String,
        user: UserModel.fromJson(json['user'] as Map<String, dynamic>),
      );

  final String accessToken;
  final String refreshToken;
  final UserModel user;
}
