/// Dùng chung cho test: tạo JWT giả (JwtDecoder không kiểm chứng chữ ký — chỉ decode).
library;

import 'dart:convert';

String makeJwt(Map<String, dynamic> claims) {
  String enc(Object o) =>
      base64Url.encode(utf8.encode(jsonEncode(o))).replaceAll('=', '');
  return '${enc(<String, String>{'alg': 'HS256'})}.${enc(claims)}.sig';
}
