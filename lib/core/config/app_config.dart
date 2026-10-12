/// Cấu hình build-time — truyền bằng --dart-define, không hardcode trong code.
///
/// Ví dụ chạy:
/// ```
/// flutter run \
///   --dart-define=API_BASE_URL=http://localhost:8000 \
///   --dart-define=GOOGLE_WEB_CLIENT_ID=xxxx.apps.googleusercontent.com \
///   --dart-define=GOOGLE_DESKTOP_CLIENT_ID=yyyy.apps.googleusercontent.com \
///   --dart-define=GOOGLE_IOS_CLIENT_ID=zzzz.apps.googleusercontent.com
/// ```
library;

import 'dart:io';

class AppConfig {
  AppConfig._();

  /// Base URL backend. Mặc định: Android emulator trỏ 10.0.2.2 (localhost máy),
  /// nền khác dùng localhost. Đặt biến môi trường API_BASE_URL để ghi đè.
  static String get apiBaseUrl {
    const String defined = String.fromEnvironment('API_BASE_URL');
    if (defined.isNotEmpty) return defined;
    if (Platform.isAndroid) return 'http://10.0.2.2:8000';
    return 'http://localhost:8000';
  }

  /// Web client ID — dùng làm serverClientId để Google trả id_token trên mobile.
  static const String googleWebClientId =
      String.fromEnvironment('GOOGLE_WEB_CLIENT_ID');

  /// Desktop client ID (loại "Desktop app") — cho luồng loopback + PKCE trên Windows.
  static const String googleDesktopClientId =
      String.fromEnvironment('GOOGLE_DESKTOP_CLIENT_ID');

  /// iOS client ID — khai báo GIDClientID trong Info.plist.
  static const String googleIosClientId =
      String.fromEnvironment('GOOGLE_IOS_CLIENT_ID');
}
