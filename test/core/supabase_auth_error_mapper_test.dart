import 'package:flutter_test/flutter_test.dart';
import 'package:docvaultproject/core/error/exceptions.dart';
import 'package:docvaultproject/core/network/supabase_auth_error_mapper.dart';

void main() {
  group('mapSupabaseAuthError', () {
    test('sai email/mật khẩu → "Wrong email or password"', () {
      for (final String raw in <String>[
        'Invalid login credentials',
        'invalid email or password',
      ]) {
        final Exception mapped = mapSupabaseAuthError(raw);
        expect(mapped, isA<AuthException>());
        expect(
          (mapped as AuthException).message,
          'Wrong email or password',
          reason: raw,
        );
        expect(mapped.needsEmailConfirmation, isFalse);
      }
    });

    test('email chưa xác nhận → AuthException kèm cờ needsEmailConfirmation', () {
      final Exception mapped = mapSupabaseAuthError('Email not confirmed');
      expect(mapped, isA<AuthException>());
      expect((mapped as AuthException).needsEmailConfirmation, isTrue);
      expect(mapped.message.toLowerCase(), contains('not confirmed'));
    });

    test('email đã đăng ký → báo trùng email', () {
      final Exception mapped = mapSupabaseAuthError('User already registered');
      expect(mapped, isA<AuthException>());
      expect(mapped.toString(), 'This email is already registered');
    });

    test('rate limit gửi email → hướng dẫn chờ', () {
      final Exception mapped = mapSupabaseAuthError('Email rate limit exceeded');
      expect(mapped, isA<AuthException>());
      expect(mapped.toString().toLowerCase(), contains('rate limiting'));
    });

    test('lỗi mạng → NetworkException (không phải lỗi phiên)', () {
      final Exception mapped = mapSupabaseAuthError('Failed to fetch');
      expect(mapped, isA<NetworkException>());
    });

    test('token hết hạn/refresh lỗi → AuthException hết phiên', () {
      final Exception mapped = mapSupabaseAuthError('Invalid Refresh Token');
      expect(mapped, isA<AuthException>());
      expect(mapped.toString(), 'The session has expired');
    });

    test('message lạ → giữ nguyên văn bản gốc, không nuốt lỗi', () {
      final Exception mapped = mapSupabaseAuthError('Something unexpected');
      expect(mapped, isA<AuthException>());
      expect(mapped.toString(), 'Something unexpected');
    });
  });
}
