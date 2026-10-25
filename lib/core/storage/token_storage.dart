/// Lưu trữ token bảo mật cục bộ: Keystore (Android), Keychain (iOS), DPAPI (Windows).
library;

import 'package:flutter_secure_storage/flutter_secure_storage.dart';

abstract class TokenStorage {
  Future<void> save({
    required String accessToken,
    required String refreshToken,
  });

  /// Trả về (accessToken, refreshToken) — phần tử null nếu chưa có.
  Future<(String?, String?)> read();

  Future<void> clear();
}

class SecureTokenStorage implements TokenStorage {
  static const String _accessKey = 'docuvault.access_token';
  static const String _refreshKey = 'docuvault.refresh_token';

  final FlutterSecureStorage _storage;

  SecureTokenStorage([FlutterSecureStorage? storage])
    : _storage = storage ?? const FlutterSecureStorage();

  @override
  Future<void> save({
    required String accessToken,
    required String refreshToken,
  }) async {
    await _storage.write(key: _accessKey, value: accessToken);
    await _storage.write(key: _refreshKey, value: refreshToken);
  }

  @override
  Future<(String?, String?)> read() async {
    final String? access = await _storage.read(key: _accessKey);
    final String? refresh = await _storage.read(key: _refreshKey);
    return (access, refresh);
  }

  @override
  Future<void> clear() async {
    await _storage.delete(key: _accessKey);
    await _storage.delete(key: _refreshKey);
  }
}
