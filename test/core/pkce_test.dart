import 'package:flutter_test/flutter_test.dart';
import 'package:testss/core/auth/pkce.dart';

void main() {
  test('Vector RFC 7636 Appendix B', () {
    const String verifier = 'dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk';
    expect(
      Pkce.challengeFor(verifier),
      'E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM',
    );
  });

  test('generate: verifier 64 ký tự, không có ký tự ngoài bảng unreserved', () {
    final Pkce pkce = Pkce.generate();
    expect(pkce.verifier.length, 64);
    expect(pkce.verifier, matches(RegExp(r'^[A-Za-z0-9\-._~]+$')));
    expect(pkce.challenge, Pkce.challengeFor(pkce.verifier));
    expect(pkce.challenge.contains('='), isFalse);
  });

  test('2 lần generate khác nhau', () {
    expect(Pkce.generate().verifier, isNot(Pkce.generate().verifier));
  });
}
