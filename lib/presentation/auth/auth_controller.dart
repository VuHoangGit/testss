/// Trạng thái xác thực của app: null = chưa đăng nhập; AsyncLoading lúc mở app.
library;

import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../domain/entities/user.dart';
import '../../domain/repositories/auth_repository.dart';
import '../providers.dart';

class AuthController extends AsyncNotifier<AuthSession?> {
  StreamSubscription<AuthSession?>? _subscription;

  @override
  FutureOr<AuthSession?> build() {
    final AuthRepository repo = ref.watch(authRepositoryProvider);
    // Mọi thay đổi phiên (đăng nhập popup Google, token refresh, đăng xuất ở
    // tab khác) đều tự đẩy state mới — controller không cần biết nguồn phát.
    _subscription = repo.sessionChanged.listen((AuthSession? session) {
      state = AsyncValue<AuthSession?>.data(session);
    });
    ref.onDispose(() => _subscription?.cancel());
    return repo.currentSession();
  }

  /// Đăng nhập email/mật khẩu. Lỗi KHÔNG đưa vào state (tránh AuthGate hiện
  /// màn hình lỗi toàn màn) — ném lại để LoginScreen hiện SnackBar.
  Future<void> signIn({required String email, required String password}) async {
    final AuthRepository repo = ref.read(authRepositoryProvider);
    state = const AsyncValue<AuthSession?>.loading();
    try {
      final AuthSession session = await repo.login(
        email: email,
        password: password,
      );
      state = AsyncValue<AuthSession?>.data(session);
    } on Exception {
      // Về trạng thái chưa đăng nhập → ở lại màn hình login
      state = const AsyncValue<AuthSession?>.data(null);
      rethrow;
    }
  }

  /// Đăng ký tài khoản. Không đổi state (vẫn chưa đăng nhập); lỗi ném về UI.
  Future<void> signUp({
    required String email,
    required String password,
    String? name,
  }) async {
    await ref
        .read(authRepositoryProvider)
        .register(email: email, password: password, name: name);
  }

  /// Đăng nhập Google (OAuth popup/redirect qua Supabase). Phiên khi có sẽ
  /// về qua sessionChanged — ở đây không tự set state.
  Future<void> signInWithGoogle() async {
    await ref.read(authRepositoryProvider).signInWithGoogle();
  }

  /// Đăng xuất chủ động: xóa phiên local + thu hồi refresh token Supabase.
  /// State về null cũng đến từ sessionChanged — set tại đây cho chắc.
  Future<void> signOut() async {
    final AuthRepository repo = ref.read(authRepositoryProvider);
    await repo.logout();
    state = const AsyncValue<AuthSession?>.data(null);
  }

  /// Server từ chối phiên (refresh fail) — chỉ dọn local, không gọi mạng.
  Future<void> forceSignOut() async {
    final AuthRepository repo = ref.read(authRepositoryProvider);
    await repo.clearLocal();
    state = const AsyncValue<AuthSession?>.data(null);
  }
}
