/// Trạng thái xác thực của app: null = chưa đăng nhập; AsyncLoading lúc mở app.
library;

import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../domain/entities/user.dart';
import '../../domain/repositories/auth_repository.dart';
import '../providers.dart';

class AuthController extends AsyncNotifier<AuthSession?> {
  StreamSubscription<AuthSession?>? _subscription;
  StreamSubscription<bool>? _recoverySubscription;

  @override
  FutureOr<AuthSession?> build() {
    final AuthRepository repo = ref.watch(authRepositoryProvider);
    // Mọi thay đổi phiên (đăng nhập popup Google, token refresh, đăng xuất ở
    // tab khác) đều tự đẩy state mới — controller không cần biết nguồn phát.
    _subscription = repo.sessionChanged.listen((AuthSession? session) {
      state = AsyncValue<AuthSession?>.data(session);
    });
    // Phiên đến từ link "Quên mật khẩu" → bật cờ để AuthGate hiện màn đặt
    // mật khẩu mới thay vì app chính.
    _recoverySubscription = repo.passwordRecoveryChanged.listen((_) {
      ref.read(passwordRecoveryProvider.notifier).set(true);
    });
    ref.onDispose(() {
      _subscription?.cancel();
      _recoverySubscription?.cancel();
    });
    return repo.currentSession();
  }

  /// Đăng nhập email/mật khẩu.
  ///
  /// KHÔNG đụng vào state khi bắt đầu: AuthGate đang hiện LoginScreen, đổi state
  /// sang loading sẽ tháo LoginScreen khỏi cây widget — mất chữ người dùng đã gõ
  /// và SnackBar lỗi không hiện được (lỗi rơi vào State đã dispose), người dùng
  /// chỉ thấy form trắng, giống hệt "tự nhiên bị đá về trang đăng nhập".
  /// Chỉ set state khi có phiên thật; lỗi ném thẳng về LoginScreen.
  Future<void> signIn({required String email, required String password}) async {
    final AuthRepository repo = ref.read(authRepositoryProvider);
    final AuthSession session = await repo.login(
      email: email,
      password: password,
    );
    state = AsyncValue<AuthSession?>.data(session);
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

  /// Gửi email đặt lại mật khẩu; lỗi ném về UI để hiện SnackBar.
  Future<void> sendPasswordReset(String email) async {
    await ref.read(authRepositoryProvider).sendPasswordReset(email);
  }

  /// Lưu tên hiển thị từ màn đặt tên. Thành công thì state đổi sang phiên đã có
  /// tên → AuthGate tự chuyển vào app chính (không cần Navigator).
  Future<void> setDisplayName(String name) async {
    final AuthSession session = await ref
        .read(authRepositoryProvider)
        .updateDisplayName(name);
    state = AsyncValue<AuthSession?>.data(session);
  }

  /// Hoàn tất đặt lại mật khẩu (từ link recovery): đổi mật khẩu → đăng xuất
  /// local → về màn đăng nhập. Lỗi đổi mật khẩu ném về UI.
  Future<void> completePasswordReset(String newPassword) async {
    final AuthRepository repo = ref.read(authRepositoryProvider);
    await repo.updatePassword(newPassword);
    await repo.clearLocal();
    ref.read(passwordRecoveryProvider.notifier).set(false);
    state = const AsyncValue<AuthSession?>.data(null);
  }
}

/// true khi phiên hiện tại đến từ link "Quên mật khẩu" (recovery).
final NotifierProvider<PasswordRecoveryController, bool>
passwordRecoveryProvider = NotifierProvider<PasswordRecoveryController, bool>(
  PasswordRecoveryController.new,
);

class PasswordRecoveryController extends Notifier<bool> {
  @override
  bool build() => false;

  void set(bool value) => state = value;
}
