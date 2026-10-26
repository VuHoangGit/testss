/// Cấu hình build-time — truyền bằng --dart-define, không hardcode trong code.
///
/// Ví dụ chạy:
/// ```
/// flutter run \
///   --dart-define=API_BASE_URL=http://localhost:8000/api/v1 \
///   --dart-define=SUPABASE_URL=https://<ref>.supabase.co \
///   --dart-define=SUPABASE_ANON_KEY=<publishable key>
/// ```
library;

import 'package:flutter/foundation.dart';

class AppConfig {
  AppConfig._();

  /// Base URL backend (đã gồm tiền tố /api/v1). Web chạy ở Edge/Chrome dùng
  /// localhost; Android emulator trỏ 10.0.2.2 (localhost của máy). Ghi đè bằng
  /// --dart-define=API_BASE_URL=... (phải gồm /api/v1, vd http://10.0.2.2:8000/api/v1).
  static String get apiBaseUrl {
    const String defined = String.fromEnvironment('API_BASE_URL');
    if (defined.isNotEmpty) return defined;
    if (kIsWeb) return 'http://localhost:8000/api/v1';
    if (defaultTargetPlatform == TargetPlatform.android && !kIsWeb) {
      return 'http://10.0.2.2:8000/api/v1';
    }
    return 'http://localhost:8000/api/v1';
  }

  /// URL project Supabase (Auth) — Supabase Dashboard → Settings → API.
  static const String supabaseUrl = String.fromEnvironment('SUPABASE_URL');

  /// Publishable key của project (public, KHÔNG phải secret key — key secret
  /// chỉ nằm phía server và app này không dùng).
  static const String supabaseAnonKey = String.fromEnvironment(
    'SUPABASE_ANON_KEY',
  );

  /// Origin hiện tại của app — dùng làm đích redirect sau khi OAuth.
  /// Trên web lấy từ URL thanh địa chỉ (đúng cả khi đổi port dev).
  static String get appOrigin =>
      kIsWeb ? Uri.base.origin : 'http://localhost:53123';
}
