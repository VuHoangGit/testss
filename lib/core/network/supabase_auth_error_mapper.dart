/// Map lỗi Supabase Auth sang exception nghiệp vụ của app.
///
/// Tách khỏi repository để unit test được mà không cần khởi tạo Supabase —
/// toàn bộ quy tắc "message tiếng Anh thân thiện" nằm ở một chỗ duy nhất.
library;

import '../error/exceptions.dart';

/// Chuyển message thô Supabase Auth trả về thành exception của app.
///
/// [raw] là `AuthException.message` của SDK (vd "Invalid login credentials").
/// Không nhận ra thì giữ nguyên message gốc để không giấu lỗi thật.
Exception mapSupabaseAuthError(String raw) {
  final String text = raw.toLowerCase();
  if (text.contains('already registered')) {
    return const AuthException('This email is already registered');
  }
  // Supabase trả "Invalid login credentials" cho cả sai email lẫn sai mật khẩu
  // (không tiết lộ email nào tồn tại) — app cũng báo gộp như vậy.
  if (text.contains('invalid login credentials') ||
      text.contains('invalid email or password')) {
    return const AuthException('Wrong email or password');
  }
  if (text.contains('email not confirmed')) {
    return const AuthException(
      'Email not confirmed — open your inbox and click the confirmation link',
      needsEmailConfirmation: true,
    );
  }
  // Gói free của Supabase giới hạn số email gửi mỗi giờ (đăng ký/reset)
  if (text.contains('rate limit')) {
    return const AuthException(
      'The sign-in server is rate limiting emails — wait a few minutes and try again',
    );
  }
  // Lỗi mạng ở tầng SDK Supabase (fetch bị chặn, mất mạng, project URL sai) —
  // nói rõ là Supabase chứ KHÔNG phải API của mình, để không đi sửa nhầm chỗ.
  if (text.contains('failed to fetch') ||
      text.contains('network') ||
      text.contains('retryable')) {
    return const NetworkException(
      'Could not reach Supabase Auth — check your internet connection and that '
      'the Supabase project URL/key are correct',
    );
  }
  // Supabase lúc viết "refresh_token", lúc viết "Invalid Refresh Token" (có dấu
  // cách) — chấp nhận cả hai dạng để không lọt xuống nhánh message thô.
  if (text.contains('refresh token') ||
      text.contains('refresh_token') ||
      text.contains('jwt expired')) {
    return const AuthException('The session has expired');
  }
  return AuthException(raw);
}
