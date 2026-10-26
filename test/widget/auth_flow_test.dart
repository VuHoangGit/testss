import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:testss/core/error/exceptions.dart';
import 'package:testss/domain/entities/user.dart';
import 'package:testss/domain/repositories/auth_repository.dart';
import 'package:testss/main.dart';
import 'package:testss/presentation/providers.dart';

class _FakeAuthRepository implements AuthRepository {
  _FakeAuthRepository();

  int loginCount = 0;
  int registerCount = 0;
  int logoutCount = 0;
  int googleCount = 0;
  bool failRegister = false;

  final StreamController<AuthSession?> _changes =
      StreamController<AuthSession?>.broadcast();

  @override
  String? get cachedAccessToken => 'fake';

  @override
  Stream<AuthSession?> get sessionChanged => _changes.stream;

  @override
  Future<AuthSession?> currentSession() async => null;

  @override
  Future<void> clearLocal() async {}

  @override
  Future<AuthSession> login({
    required String email,
    required String password,
  }) async {
    loginCount++;
    await Future<void>.delayed(const Duration(milliseconds: 50));
    return _session(email, null);
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
  Future<void> logout() async => logoutCount++;

  @override
  Future<AuthSession> refreshSession() async => throw UnimplementedError();

  AuthSession _session(String email, String? name) => AuthSession(
    user: User(id: 'u-1', email: email, name: name ?? 'Tester'),
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

  testWidgets('Bấm "Continue with Google" → gọi signInWithGoogle, chưa vào Shell', (
    WidgetTester tester,
  ) async {
    final _FakeAuthRepository repo = _FakeAuthRepository();
    await tester.pumpWidget(await _app(repo));
    await tester.pumpAndSettle();

    await tester.tap(find.text('Continue with Google'));
    await tester.pump();

    expect(repo.googleCount, 1);
    // Session sẽ về qua sessionChanged — ở đây chưa có nên vẫn ở Login
    expect(find.text('Sign in'), findsOneWidget);
  });

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
}
