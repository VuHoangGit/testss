import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:docvaultproject/core/error/exceptions.dart';
import 'package:docvaultproject/domain/entities/user.dart';
import 'package:docvaultproject/domain/repositories/auth_repository.dart';
import 'package:docvaultproject/main.dart';
import 'package:docvaultproject/presentation/providers.dart';

class _FakeAuthRepository implements AuthRepository {
  _FakeAuthRepository();

  int loginCount = 0;
  int registerCount = 0;
  int logoutCount = 0;
  int googleCount = 0;
  int resetEmailCount = 0;
  int updatePasswordCount = 0;
  bool failRegister = false;
  bool failLogin = false;
  List<String> resetEmails = <String>[];

  final StreamController<AuthSession?> _changes =
      StreamController<AuthSession?>.broadcast();
  final StreamController<bool> _recovery = StreamController<bool>.broadcast();

  @override
  String? get cachedAccessToken => 'fake';

  @override
  Stream<AuthSession?> get sessionChanged => _changes.stream;

  @override
  Stream<bool> get passwordRecoveryChanged => _recovery.stream;

  /// true = đã có phiên (dùng cho test luồng recovery link).
  bool hasSession = false;

  @override
  Future<AuthSession?> currentSession() async =>
      hasSession ? _session('hoang@gmail.com', null) : null;

  int clearLocalCount = 0;

  @override
  Future<void> clearLocal() async => clearLocalCount++;

  @override
  Future<AuthSession> login({
    required String email,
    required String password,
  }) async {
    loginCount++;
    lastEmail = email;
    await Future<void>.delayed(const Duration(milliseconds: 50));
    if (failLogin) {
      // Repository production map lỗi Supabase thành đúng message này
      throw const AuthException('Wrong email or password');
    }
    return _session(email, null);
  }

  /// false = lần đăng nhập đầu tiên → app phải hỏi tên hiển thị.
  bool nameChosen = true;
  String lastEmail = 'hoang@gmail.com';
  List<String> savedNames = <String>[];

  @override
  Future<AuthSession> updateDisplayName(String name) async {
    savedNames.add(name);
    nameChosen = true;
    return _session(lastEmail, name);
  }

  @override
  Future<void> register({
    required String email,
    required String password,
    String? name,
  }) async {
    registerCount++;
    if (failRegister) {
      throw const AuthException('Email đã được đăng ký');
    }
  }

  @override
  Future<void> signInWithGoogle() async => googleCount++;

  @override
  Future<void> sendPasswordReset(String email) async {
    resetEmailCount++;
    resetEmails.add(email);
  }

  @override
  Future<void> updatePassword(String password) async => updatePasswordCount++;

  /// Giả lập user mở link "Quên mật khẩu" trong email.
  void emitRecovery() => _recovery.add(true);

  @override
  Future<void> logout() async => logoutCount++;

  @override
  Future<AuthSession> refreshSession() async => throw UnimplementedError();

  AuthSession _session(String email, String? name) => AuthSession(
    user: User(
      id: 'u-1',
      email: email,
      name: name ?? 'Tester',
      nameChosen: nameChosen,
    ),
    accessToken: 'fake-access',
  );
}

Future<Widget> _app(_FakeAuthRepository repo) async => ProviderScope(
  overrides: [authRepositoryProvider.overrideWithValue(repo)],
  child: const DocuVaultApp(),
);

void main() {
  testWidgets('Đăng nhập email/mật khẩu → Shell', (WidgetTester tester) async {
    final _FakeAuthRepository repo = _FakeAuthRepository();
    await tester.pumpWidget(await _app(repo));
    await tester.pumpAndSettle();

    expect(find.text('DocuVault'), findsWidgets);
    expect(find.text('Sign in'), findsOneWidget);

    await tester.enterText(find.byType(TextFormField).at(0), 'hoang@gmail.com');
    await tester.enterText(find.byType(TextFormField).at(1), '123456');
    await tester.tap(find.widgetWithText(FilledButton, 'Sign in'));
    await tester.pumpAndSettle();

    expect(repo.loginCount, 1);
    expect(find.textContaining('Good morning'), findsOneWidget);
    expect(find.text('Files'), findsOneWidget);
  });

  testWidgets('Đăng nhập lần đầu → màn đặt tên → đặt xong mới vào app chính', (
    WidgetTester tester,
  ) async {
    // nameChosen = false: backend trả name_chosen_at = null (chưa tự đặt tên)
    final _FakeAuthRepository repo = _FakeAuthRepository()..nameChosen = false;
    await tester.pumpWidget(await _app(repo));
    await tester.pumpAndSettle();

    await tester.enterText(find.byType(TextFormField).at(0), 'hoang@gmail.com');
    await tester.enterText(find.byType(TextFormField).at(1), '123456');
    await tester.tap(find.widgetWithText(FilledButton, 'Sign in'));
    await tester.pumpAndSettle();

    // Đăng nhập xong CHƯA vào app chính: phải đặt tên trước, ô nhập điền sẵn
    // tên Google (chỉ là gợi ý, sửa được).
    expect(find.text('What should we call you?'), findsOneWidget);
    expect(find.textContaining('Good morning'), findsNothing);
    expect(find.text('Tester'), findsOneWidget);

    await tester.enterText(find.byType(TextFormField), 'Hoàng Vũ');
    await tester.tap(find.widgetWithText(FilledButton, 'Continue'));
    await tester.pumpAndSettle();

    expect(repo.savedNames, <String>['Hoàng Vũ']);
    expect(find.textContaining('Good morning'), findsOneWidget);
    expect(find.text('What should we call you?'), findsNothing);
  });

  testWidgets('Tên để trống → báo lỗi tại chỗ, không gọi server', (
    WidgetTester tester,
  ) async {
    final _FakeAuthRepository repo = _FakeAuthRepository()..nameChosen = false;
    await tester.pumpWidget(await _app(repo));
    await tester.pumpAndSettle();

    await tester.enterText(find.byType(TextFormField).at(0), 'hoang@gmail.com');
    await tester.enterText(find.byType(TextFormField).at(1), '123456');
    await tester.tap(find.widgetWithText(FilledButton, 'Sign in'));
    await tester.pumpAndSettle();

    await tester.enterText(find.byType(TextFormField), '   ');
    await tester.tap(find.widgetWithText(FilledButton, 'Continue'));
    await tester.pumpAndSettle();

    expect(find.text('Enter your name'), findsOneWidget);
    expect(repo.savedNames, isEmpty);
  });

  testWidgets(
    'REG-1: sai mật khẩu → vẫn ở Login, báo "Wrong email or password", giữ email',
    (WidgetTester tester) async {
      final _FakeAuthRepository repo = _FakeAuthRepository()..failLogin = true;
      await tester.pumpWidget(await _app(repo));
      await tester.pumpAndSettle();

      await tester.enterText(
        find.byType(TextFormField).at(0),
        'hoang@gmail.com',
      );
      await tester.enterText(find.byType(TextFormField).at(1), 'sai-mat-khau');
      await tester.tap(find.widgetWithText(FilledButton, 'Sign in'));

      // Đăng nhập chạy 50ms rồi ném lỗi; trước đây AuthGate bị đổi state sang
      // loading nên LoginScreen bị tháo khỏi cây widget, SnackBar lỗi mất và
      // form trắng trơn (người dùng tưởng "tự refresh về trang đăng nhập").
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));
      await tester.pumpAndSettle();

      expect(repo.loginCount, 1);
      expect(find.text('Wrong email or password'), findsOneWidget);
      // vẫn ở màn đăng nhập và không mất chữ đã gõ
      expect(find.widgetWithText(FilledButton, 'Sign in'), findsOneWidget);
      expect(find.text('hoang@gmail.com'), findsOneWidget);
    },
  );

  testWidgets('Đăng ký → quay lại form đăng nhập kèm thông báo', (
    WidgetTester tester,
  ) async {
    final _FakeAuthRepository repo = _FakeAuthRepository();
    await tester.pumpWidget(await _app(repo));
    await tester.pumpAndSettle();

    // chuyển sang chế độ đăng ký
    await tester.tap(find.text('New to DocuVault? Create an account'));
    await tester.pumpAndSettle();
    expect(find.widgetWithText(FilledButton, 'Create account'), findsOneWidget);

    await tester.enterText(find.byType(TextFormField).at(0), 'hoang@gmail.com');
    await tester.enterText(find.byType(TextFormField).at(2), '123456');
    await tester.tap(find.widgetWithText(FilledButton, 'Create account'));
    await tester.pump(); // snackbar + setState

    expect(repo.registerCount, 1);
    // về lại form đăng nhập, email giữ sẵn
    expect(find.widgetWithText(FilledButton, 'Sign in'), findsOneWidget);
    expect(
      find.text('Account created successfully. Please sign in.'),
      findsOneWidget,
    );
  });

  testWidgets('Đăng ký trùng email → SnackBar lỗi, ở lại màn hình', (
    WidgetTester tester,
  ) async {
    final _FakeAuthRepository repo = _FakeAuthRepository()..failRegister = true;
    await tester.pumpWidget(await _app(repo));
    await tester.pumpAndSettle();

    await tester.tap(find.text('New to DocuVault? Create an account'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextFormField).at(0), 'hoang@gmail.com');
    await tester.enterText(find.byType(TextFormField).at(2), '123456');
    await tester.tap(find.widgetWithText(FilledButton, 'Create account'));
    await tester.pump();

    expect(find.text('Email đã được đăng ký'), findsOneWidget);
    // vẫn ở chế độ đăng ký
    expect(find.widgetWithText(FilledButton, 'Create account'), findsOneWidget);
  });

  testWidgets(
    'Bấm "Continue with Google" → gọi signInWithGoogle, chưa vào Shell',
    (WidgetTester tester) async {
      final _FakeAuthRepository repo = _FakeAuthRepository();
      await tester.pumpWidget(await _app(repo));
      await tester.pumpAndSettle();

      await tester.tap(find.text('Continue with Google'));
      await tester.pump();

      expect(repo.googleCount, 1);
      // Session sẽ về qua sessionChanged — ở đây chưa có nên vẫn ở Login
      expect(find.text('Sign in'), findsOneWidget);
    },
  );

  testWidgets('L4: logout có xác nhận → về Login', (WidgetTester tester) async {
    final _FakeAuthRepository repo = _FakeAuthRepository();
    await tester.pumpWidget(await _app(repo));
    await tester.pumpAndSettle();

    // vào Shell bằng đăng nhập email/mật khẩu qua UI
    await tester.enterText(find.byType(TextFormField).at(0), 'a@gmail.com');
    await tester.enterText(find.byType(TextFormField).at(1), '123456');
    await tester.tap(find.widgetWithText(FilledButton, 'Sign in'));
    await tester.pumpAndSettle();

    // sang tab Tài khoản — với cửa sổ test hẹp thì là NavigationBar
    await tester.tap(find.text('Account').last);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Sign out'));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, 'Sign out'));
    await tester.pumpAndSettle();

    expect(repo.logoutCount, 1);
    expect(find.widgetWithText(FilledButton, 'Sign in'), findsOneWidget);
  });

  testWidgets('Quên mật khẩu: dialog nhập email → gửi reset + snackbar', (
    WidgetTester tester,
  ) async {
    final _FakeAuthRepository repo = _FakeAuthRepository();
    await tester.pumpWidget(await _app(repo));
    await tester.pumpAndSettle();

    await tester.tap(find.text('Forgot password?'));
    await tester.pumpAndSettle();
    expect(find.text('Reset password'), findsOneWidget);

    // TextField cuối cùng = của dialog (đè lên form login)
    await tester.enterText(find.byType(TextField).last, 'hoang@gmail.com');
    await tester.tap(find.widgetWithText(FilledButton, 'Send email'));
    await tester.pump();

    expect(repo.resetEmailCount, 1);
    expect(repo.resetEmails.first, 'hoang@gmail.com');
    expect(find.text('Reset email sent — check your inbox.'), findsOneWidget);
    expect(find.text('Sign in'), findsOneWidget); // vẫn ở màn login
  });

  testWidgets('Link recovery → màn đặt mật khẩu mới → về Login', (
    WidgetTester tester,
  ) async {
    final _FakeAuthRepository repo = _FakeAuthRepository()..hasSession = true;
    await tester.pumpWidget(await _app(repo));
    await tester.pumpAndSettle();

    // Mở link "Quên mật khẩu" → event recovery → AuthGate đổi màn
    repo.emitRecovery();
    await tester.pumpAndSettle();
    expect(find.text('Set a new password'), findsOneWidget);

    await tester.enterText(find.byType(TextFormField).at(0), 'newpass123');
    await tester.enterText(find.byType(TextFormField).at(1), 'newpass123');
    await tester.tap(find.widgetWithText(FilledButton, 'Update password'));
    await tester.pumpAndSettle();

    expect(repo.updatePasswordCount, 1);
    expect(repo.clearLocalCount, 1); // đăng xuất local sau khi đổi mật khẩu
    expect(find.widgetWithText(FilledButton, 'Sign in'), findsOneWidget);
  });
}
