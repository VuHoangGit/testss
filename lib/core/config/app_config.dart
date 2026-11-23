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

import 'server_url_store.dart';

class AppConfig {
  AppConfig._();

  /// Base URL backend mặc định theo build/nền, chưa tính phần ghi đè của
  /// người dùng. Web chạy ở Edge/Chrome dùng localhost; Android emulator trỏ
  /// 10.0.2.2 (localhost của máy). Ghi đè bằng --dart-define=API_BASE_URL=...
  /// (phải gồm /api/v1, vd http://10.0.2.2:8000/api/v1).
  static String get defaultApiBaseUrl {
    const String defined = String.fromEnvironment('API_BASE_URL');
    if (defined.isNotEmpty) return defined;
    if (kIsWeb && Uri.base.host.endsWith('ngrok-free.dev')) {
      return '${Uri.base.scheme}://${Uri.base.host}/api/v1';
    }
    if (kIsWeb) return 'http://localhost:8000/api/v1';
    if (defaultTargetPlatform == TargetPlatform.android && !kIsWeb) {
      return 'http://10.0.2.2:8000/api/v1';
    }
    return 'http://localhost:8000/api/v1';
  }

  /// Địa chỉ backend người dùng tự nhập trong ô "Server" (đã chuẩn hóa, gồm
  /// /api/v1), lưu localStorage của trình duyệt — chỉ có trên web.
  static String? get serverUrlOverride => readServerUrlOverride();

  /// Base URL backend (đã gồm tiền tố /api/v1) dùng cho Dio: địa chỉ người
  /// dùng nhập được ưu tiên hơn mặc định build-time, để mở app trên điện
  /// thoại qua IP LAN mà không cần build lại.
  static String get apiBaseUrl => serverUrlOverride ?? defaultApiBaseUrl;

  /// API public share dùng chung origin của máy chủ đang phục vụ web.
  /// Dev: thay port 53123 bằng backend 8000; production: giữ port origin.
  static String get publicShareApiBaseUrl {
    if (!kIsWeb) return defaultApiBaseUrl;
    final Uri origin = Uri.base;
    if (origin.host.endsWith('ngrok-free.dev')) {
      return '${origin.scheme}://${origin.host}/api/v1';
    }
    final bool localDev =
        origin.host == 'localhost' ||
        origin.host == '127.0.0.1' ||
        origin.host.startsWith('192.168.') ||
        origin.host.startsWith('10.') ||
        origin.host.startsWith('172.');
    if (localDev) {
      return '${origin.scheme}://${origin.host}:8000/api/v1';
    }
    return '${origin.scheme}://${origin.host}${origin.hasPort ? ':${origin.port}' : ''}/api/v1';
  }

  /// Chuẩn hóa địa chỉ máy chủ người dùng nhập: thêm http:// khi thiếu scheme,
  /// bỏ path/query, ghép /api/v1. Ném [FormatException] (message tiếng Anh
  /// hiển thị ngay trong dialog) khi địa chỉ không dùng được.
  static String normalizeServerUrl(String input) {
    String raw = input.trim();
    if (raw.isEmpty) {
      throw const FormatException('Enter a server address');
    }
    final bool hasScheme =
        raw.startsWith('http://') || raw.startsWith('https://');
    if (!hasScheme) {
      if (raw.contains('://')) {
        throw const FormatException('Only http:// and https:// are supported');
      }
      raw = 'http://$raw';
    }
    final Uri? uri = Uri.tryParse(raw);
    if (uri == null || !uri.hasScheme || uri.host.isEmpty) {
      throw const FormatException('Invalid server address');
    }
    // Uri.tryParse khoan dung với ký tự lạ (dấu cách bị mã hóa %20 trong
    // host) — host phải chỉ gồm chữ/số/dấu chấm/gạch nối mới dùng được.
    if (!RegExp(r'^[a-zA-Z0-9]([a-zA-Z0-9.-]*[a-zA-Z0-9])?$')
        .hasMatch(uri.host)) {
      throw const FormatException('Invalid server address');
    }
    final String port = uri.hasPort ? ':${uri.port}' : '';
    return '${uri.scheme}://${uri.host}$port/api/v1';
  }

  /// URL project Supabase (Auth) — Supabase Dashboard → Settings → API.
  /// Ưu tiên dart-define; thiếu thì dùng project dev mặc định để `flutter run`
  /// không dart-define vẫn chạy được (tránh "No host specified in URI" khi
  /// đăng nhập). Đổi project khác → truyền SUPABASE_URL như thường.
  static String get supabaseUrl {
    const String defined = String.fromEnvironment('SUPABASE_URL');
    return defined.isNotEmpty
        ? defined
        : 'https://coryhhxuexvnqkdgkvtj.supabase.co';
  }

  /// Publishable key của project (public, KHÔNG phải secret key — key secret
  /// chỉ nằm phía server và app này không dùng). Tương tự supabaseUrl: có
  /// sẵn mặc định dev, dart-define đè được.
  static String get supabaseAnonKey {
    const String defined = String.fromEnvironment('SUPABASE_ANON_KEY');
    return defined.isNotEmpty
        ? defined
        : 'sb_publishable_xhHfd7VtTUeoiK3gE1dnSQ_Vt-BxRCu';
  }

  /// Origin hiện tại của app — dùng làm đích redirect sau khi OAuth.
  /// Trên web lấy từ URL thanh địa chỉ (đúng cả khi đổi port dev).
  static String get appOrigin =>
      kIsWeb ? Uri.base.origin : 'http://localhost:53123';
}
