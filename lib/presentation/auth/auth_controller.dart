/// Trạng thái xác thực của app: null = chưa đăng nhập; AsyncLoading lúc mở app.
library;

import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../domain/entities/user.dart';
import '../../domain/repositories/auth_repository.dart';
import '../providers.dart';

class AuthController extends AsyncNotifier<AuthSession?> {
  @override
  FutureOr<AuthSession?> build() {
    final AuthRepository repo = ref.watch(authRepositoryProvider);
    return repo.restore();
  }

  /// Đăng nhập nhanh (dev) — thay bằng luồng Google sau khi cấu hình OAuth.
  Future<void> signInDev({required String email, String? name}) async {
    final AuthRepository repo = ref.read(authRepositoryProvider);
    state = const AsyncValue<AuthSession?>.loading();
    try {
      final AuthSession session =
          await repo.devLogin(email: email, name: name);
      state = AsyncValue<AuthSession?>.data(session);
    } on Exception catch (e, st) {
      state = AsyncValue<AuthSession?>.error(e, st);
    }
  }

  /// Đăng xuất chủ động: revoke server (best-effort) + xóa local.
  Future<void> signOut() async {
    final AuthRepository repo = ref.read(authRepositoryProvider);
    await repo.logout();
    state = const AsyncValue<AuthSession?>.data(null);
  }

  /// Server từ chối phiên (refresh fail vì 401) — chỉ dọn local, không gọi mạng.
  Future<void> forceSignOut() async {
    final AuthRepository repo = ref.read(authRepositoryProvider);
    await repo.clearLocal();
    state = const AsyncValue<AuthSession?>.data(null);
  }
}
