import 'package:flutter_test/flutter_test.dart';
import 'package:testss/core/error/exceptions.dart';
import 'package:testss/core/network/session_refresher.dart';

void main() {
  test('N lời gọi song song → refresh chỉ chạy đúng 1 lần (EC-31)', () async {
    final SessionRefresher refresher = SessionRefresher();
    int count = 0;

    final List<Future<void>> futures = <Future<void>>[
      refresher.run(() async {
        count++;
        await Future<void>.delayed(const Duration(milliseconds: 30));
      }),
      refresher.run(() async {
        count++;
        await Future<void>.delayed(const Duration(milliseconds: 30));
      }),
      refresher.run(() async {
        count++;
        await Future<void>.delayed(const Duration(milliseconds: 30));
      }),
    ];
    await Future.wait(futures);
    expect(count, 1);
  });

  test('refresh fail → mọi caller nhận lỗi; lần gọi SAU chạy lại bình thường', () async {
    final SessionRefresher refresher = SessionRefresher();
    int count = 0;

    final List<Future<void>> futures = <Future<void>>[
      refresher.run(() async {
        count++;
        throw const AuthException('hết hạn');
      }),
      refresher.run(() async {
        count++;
        throw const AuthException('hết hạn');
      }),
    ];
    for (final Future<void> f in futures) {
      await expectLater(f, throwsA(isA<AuthException>()));
    }
    expect(count, 1); // single-flight: 2 caller, 1 lần chạy

    // in-flight đã dọn → chạy lại được
    await refresher.run(() async => count++);
    expect(count, 2);
  });
}
