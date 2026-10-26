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
