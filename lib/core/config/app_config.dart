/// Cấu hình build-time — truyền bằng --dart-define, không hardcode trong code.
///
/// Ví dụ chạy:
/// ```
/// flutter run --dart-define=API_BASE_URL=http://localhost:8000
/// ```
library;

import 'package:flutter/foundation.dart';

class AppConfig {
  AppConfig._();

  /// Base URL backend. Web chạy ở Edge/Chrome dùng localhost; Android emulator
  /// trỏ 10.0.2.2 (localhost của máy). Ghi đè bằng --dart-define=API_BASE_URL=...
  static String get apiBaseUrl {
    const String defined = String.fromEnvironment('API_BASE_URL');
    if (defined.isNotEmpty) return defined;
    if (kIsWeb) return 'http://localhost:8000';
    if (defaultTargetPlatform == TargetPlatform.android && !kIsWeb) {
      return 'http://10.0.2.2:8000';
    }
    return 'http://localhost:8000';
  }

  /// Web client ID (Google OAuth) — dùng khi tích hợp đăng nhập Google thật.
  static const String googleWebClientId =
      String.fromEnvironment('GOOGLE_WEB_CLIENT_ID');

  /// Desktop client ID — cho luồng loopback + PKCE trên Windows (google_sign_in
  /// không hỗ trợ Windows; xem lib/core/auth/desktop_google_sign_in.dart).
  static const String googleDesktopClientId =
      String.fromEnvironment('GOOGLE_DESKTOP_CLIENT_ID');

  /// iOS client ID — khai báo GIDClientID trong Info.plist khi tích hợp.
  static const String googleIosClientId =
      String.fromEnvironment('GOOGLE_IOS_CLIENT_ID');
}
