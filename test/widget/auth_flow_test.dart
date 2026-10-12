import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:testss/domain/entities/user.dart';
import 'package:testss/domain/repositories/auth_repository.dart';
import 'package:testss/main.dart';
import 'package:testss/presentation/providers.dart';

class _FakeAuthRepository implements AuthRepository {
  _FakeAuthRepository();

  int devLoginCount = 0;
  int logoutCount = 0;

  @override
  String? get cachedAccessToken => 'fake';

  @override
  Future<void> clearLocal() async {}

  @override
  Future<AuthSession> devLogin({required String email, String? name}) async {
    devLoginCount++;
    await Future<void>.delayed(const Duration(milliseconds: 50));
    return AuthSession(
      user: User(id: 'u-1', email: email, name: name ?? 'Tester'),
      accessToken: 'fake-access',
      refreshToken: 'fake-refresh',
    );
  }

  @override
  Future<void> logout() async => logoutCount++;

  @override
  Future<AuthSession?> restore() async => null;

  @override
  Future<AuthSession> refreshSession() async => throw UnimplementedError();
}

Future<Widget> _app(_FakeAuthRepository repo) async => ProviderScope(
      overrides: [authRepositoryProvider.overrideWithValue(repo)],
      child: const DocuVaultApp(),
    );

void main() {
  testWidgets('L1: mở app chưa đăng nhập → Login → dev login → Shell', (WidgetTester tester) async {
    final _FakeAuthRepository repo = _FakeAuthRepository();
    await tester.pumpWidget(await _app(repo));
    await tester.pumpAndSettle();

    expect(find.text('DocuVault'), findsWidgets);
    expect(find.text('Vào ứng dụng'), findsOneWidget);

    await tester.enterText(
      find.widgetWithText(TextFormField, 'Email (đăng nhập nhanh dev)'),
      'thanhit@gmail.com',
    );
    await tester.tap(find.text('Vào ứng dụng'));
    await tester.pumpAndSettle();

    expect(repo.devLoginCount, 1);
    expect(find.textContaining('Xin chào'), findsOneWidget);
    expect(find.text('Tài liệu'), findsOneWidget); // có tab trong NavigationBar/Rail
  });

  testWidgets('L4: logout có xác nhận → về Login', (WidgetTester tester) async {
    final _FakeAuthRepository repo = _FakeAuthRepository();
    await tester.pumpWidget(await _app(repo));
    await tester.pumpAndSettle();

    // vào Shell bằng dev login qua UI cho chắc
    await tester.enterText(
      find.widgetWithText(TextFormField, 'Email (đăng nhập nhanh dev)'),
      'a@gmail.com',
    );
    await tester.tap(find.text('Vào ứng dụng'));
    await tester.pumpAndSettle();

    // sang tab Tài khoản — với cửa sổ test hẹp thì là NavigationBar
    await tester.tap(find.text('Tài khoản').last);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Đăng xuất'));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, 'Đăng xuất'));
    await tester.pumpAndSettle();

    expect(repo.logoutCount, 1);
    expect(find.text('Vào ứng dụng'), findsOneWidget);
  });
}
