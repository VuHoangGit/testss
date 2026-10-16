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
  bool failRegister = false;

  @override
  String? get cachedAccessToken => 'fake';

  @override
  Future<void> clearLocal() async {}

  @override
  Future<AuthSession> devLogin({required String email, String? name}) async =>
      _session(email, name);

  @override
  Future<AuthSession> login({required String email, required String password}) async {
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
  Future<void> logout() async => logoutCount++;

  @override
  Future<AuthSession?> restore() async => null;

  @override
  Future<AuthSession> refreshSession() async => throw UnimplementedError();

  AuthSession _session(String email, String? name) => AuthSession(
        user: User(id: 'u-1', email: email, name: name ?? 'Tester'),
        accessToken: 'fake-access',
        refreshToken: 'fake-refresh',
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
    expect(find.text('Đăng nhập'), findsOneWidget);

    await tester.enterText(
      find.widgetWithText(TextFormField, 'Email'),
      'hoang@gmail.com',
    );
    await tester.enterText(find.widgetWithText(TextFormField, 'Mật khẩu'), '123456');
    await tester.tap(find.widgetWithText(FilledButton, 'Đăng nhập'));
    await tester.pumpAndSettle();

    expect(repo.loginCount, 1);
    expect(find.textContaining('Xin chào'), findsOneWidget);
    expect(find.text('Tài liệu'), findsOneWidget); // có tab trong NavigationBar/Rail
  });

  testWidgets('Đăng ký → quay lại form đăng nhập kèm thông báo', (WidgetTester tester) async {
    final _FakeAuthRepository repo = _FakeAuthRepository();
    await tester.pumpWidget(await _app(repo));
    await tester.pumpAndSettle();

    // chuyển sang chế độ đăng ký
    await tester.tap(find.text('Chưa có tài khoản? Đăng ký'));
    await tester.pumpAndSettle();
    expect(find.widgetWithText(FilledButton, 'Đăng ký'), findsOneWidget);

    await tester.enterText(find.widgetWithText(TextFormField, 'Email'), 'hoang@gmail.com');
    await tester.enterText(find.widgetWithText(TextFormField, 'Mật khẩu'), '123456');
    await tester.tap(find.widgetWithText(FilledButton, 'Đăng ký'));
    await tester.pump(); // snackbar + setState

    expect(repo.registerCount, 1);
    // về lại form đăng nhập, email giữ sẵn
    expect(find.widgetWithText(FilledButton, 'Đăng nhập'), findsOneWidget);
    expect(find.text('Đăng ký thành công. Hãy đăng nhập.'), findsOneWidget);
  });

  testWidgets('Đăng ký trùng email → SnackBar lỗi, ở lại màn hình', (WidgetTester tester) async {
    final _FakeAuthRepository repo = _FakeAuthRepository()..failRegister = true;
    await tester.pumpWidget(await _app(repo));
    await tester.pumpAndSettle();

    await tester.tap(find.text('Chưa có tài khoản? Đăng ký'));
    await tester.pumpAndSettle();
    await tester.enterText(find.widgetWithText(TextFormField, 'Email'), 'hoang@gmail.com');
    await tester.enterText(find.widgetWithText(TextFormField, 'Mật khẩu'), '123456');
    await tester.tap(find.widgetWithText(FilledButton, 'Đăng ký'));
    await tester.pump();

    expect(find.text('Email đã được đăng ký'), findsOneWidget);
    // vẫn ở chế độ đăng ký
    expect(find.widgetWithText(FilledButton, 'Đăng ký'), findsOneWidget);
  });

  testWidgets('L4: logout có xác nhận → về Login', (WidgetTester tester) async {
    final _FakeAuthRepository repo = _FakeAuthRepository();
    await tester.pumpWidget(await _app(repo));
    await tester.pumpAndSettle();

    // vào Shell bằng đăng nhập email/mật khẩu qua UI
    await tester.enterText(find.widgetWithText(TextFormField, 'Email'), 'a@gmail.com');
    await tester.enterText(find.widgetWithText(TextFormField, 'Mật khẩu'), '123456');
    await tester.tap(find.widgetWithText(FilledButton, 'Đăng nhập'));
    await tester.pumpAndSettle();

    // sang tab Tài khoản — với cửa sổ test hẹp thì là NavigationBar
    await tester.tap(find.text('Tài khoản').last);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Đăng xuất'));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, 'Đăng xuất'));
    await tester.pumpAndSettle();

    expect(repo.logoutCount, 1);
    expect(find.widgetWithText(FilledButton, 'Đăng nhập'), findsOneWidget);
  });
}
