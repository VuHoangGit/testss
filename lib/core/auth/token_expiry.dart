/// Check hạn access token ở client, trừ leeway cho lệch giờ máy (EC-13/15).
library;

import 'package:jwt_decoder/jwt_decoder.dart';

/// Token có thể dùng tiếp không? Hết hạn trong vòng [leeway] coi như hết hạn
/// để client chủ động refresh trước khi server từ chối.
bool isAccessTokenUsable(
  String? accessToken, {
  DateTime? now,
  Duration leeway = const Duration(seconds: 60),
}) {
  if (accessToken == null || accessToken.isEmpty) return false;
  try {
    final dynamic exp = JwtDecoder.decode(accessToken)['exp'];
    if (exp is! num) return false;
    final DateTime expiresAt =
        DateTime.fromMillisecondsSinceEpoch((exp * 1000).toInt());
    final DateTime currentTime = now ?? DateTime.now();
    return currentTime.isBefore(expiresAt.subtract(leeway));
  } on FormatException {
    return false; // token sai định dạng → coi như hết hạn
  } on ArgumentError {
    return false;
  }
}
