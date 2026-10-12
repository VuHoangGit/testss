/// PKCE (RFC 7636) cho luồng đăng nhập desktop: code_verifier ngẫu nhiên +
/// code_challenge S256 gửi kèm URL đăng nhập.
library;

import 'dart:convert';
import 'dart:math';

import 'package:crypto/crypto.dart';

class Pkce {
  const Pkce(this.verifier, this.challenge);

  final String verifier;
  final String challenge;

  /// Sinh verifier 64 ký tự từ bảng unreserved (RFC 7636 yêu cầu 43–128 ký tự).
  static Pkce generate({Random? random}) {
    final Random rand = random ?? Random.secure();
    const String chars =
        'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~';
    final String verifier =
        List<String>.generate(64, (_) => chars[rand.nextInt(chars.length)]).join();
    return Pkce(verifier, challengeFor(verifier));
  }

  /// BASE64URL-ENCODE(SHA256(ASCII(code_verifier))) không kèm dấu `=`.
  static String challengeFor(String verifier) => base64Url
      .encode(sha256.convert(ascii.encode(verifier)).bytes)
      .replaceAll('=', '');
}
