import 'package:flutter_test/flutter_test.dart';
import 'package:testss/core/auth/token_expiry.dart';

import '../helpers.dart';

void main() {
  final DateTime now = DateTime.fromMillisecondsSinceEpoch(1000000000000);

  test('null/rỗng → không dùng được', () {
    expect(isAccessTokenUsable(null, now: now), isFalse);
    expect(isAccessTokenUsable('', now: now), isFalse);
  });

  test('token còn hạn (dư leeway) → dùng được', () {
    final String token = makeJwt(<String, dynamic>{
      'exp': now.millisecondsSinceEpoch ~/ 1000 + 300,
    });
    expect(isAccessTokenUsable(token, now: now), isTrue);
  });

  test('token hết hạn → không dùng được', () {
    final String token = makeJwt(<String, dynamic>{
      'exp': now.millisecondsSinceEpoch ~/ 1000 - 10,
    });
    expect(isAccessTokenUsable(token, now: now), isFalse);
  });

  test('hết hạn trong vòng leeway (EC-13) → coi như hết hạn để chủ động refresh', () {
    final String token = makeJwt(<String, dynamic>{
      'exp': now.millisecondsSinceEpoch ~/ 1000 + 30, // < leeway 60s
    });
    expect(isAccessTokenUsable(token, now: now), isFalse);
  });

  test('token rác/không phải JWT → không dùng được, không nổ exception', () {
    expect(isAccessTokenUsable('khong-phai-jwt', now: now), isFalse);
  });
}
