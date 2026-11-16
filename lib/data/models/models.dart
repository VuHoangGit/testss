/// Model tầng data: parse JSON từ backend → entity domain.
library;

import '../../domain/entities/user.dart';

class UserModel {
  const UserModel({
    required this.id,
    required this.email,
    this.name,
    this.avatarUrl,
    this.nameChosen = true,
  });

  factory UserModel.fromJson(Map<String, dynamic> json) => UserModel(
    id: json['id'] as String,
    email: json['email'] as String,
    name: json['name'] as String?,
    avatarUrl: json['avatar_url'] as String?,
    // Backend trả NULL khi người dùng chưa tự đặt tên → phải hỏi tên
    nameChosen: json['name_chosen_at'] != null,
  );

  final String id;
  final String email;
  final String? name;
  final String? avatarUrl;
  final bool nameChosen;

  User toEntity() => User(
    id: id,
    email: email,
    name: name,
    avatarUrl: avatarUrl,
    nameChosen: nameChosen,
  );
}
