/// Đăng nhập Google trên desktop (Windows) — phương án loopback + PKCE.
///
/// DEFERRED (theo yêu cầu): chưa wire vào UI — bật khi có Desktop client ID.
/// Luồng: mở trình duyệt hệ thống → Google redirect về `http://127.0.0.1:{port}`
/// → nhận `code` → đổi id_token (PKCE) → gửi backend như luồng mobile.
library;

import 'dart:math';

import 'package:dio/dio.dart';
import 'package:url_launcher/url_launcher.dart';

import '../error/exceptions.dart';
import 'loopback_oauth_server.dart';
import 'pkce.dart';

class DesktopGoogleSignIn {
  DesktopGoogleSignIn({
    required this.clientId,
    Dio? dio,
    LoopbackOAuthServer? server,
    Future<void> Function(Uri url)? openBrowser,
    Uri? tokenEndpoint,
  })  : _dio = dio ?? Dio(BaseOptions(connectTimeout: const Duration(seconds: 15))),
        _server = server ?? LoopbackOAuthServer(),
        _openBrowser = openBrowser ?? _launchInBrowser,
        _tokenEndpoint = tokenEndpoint ?? Uri.https('oauth2.googleapis.com', '/token');

  static const String _chars =
      'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';

  final String clientId;
  final Dio _dio;
  final LoopbackOAuthServer _server;
  final Future<void> Function(Uri url) _openBrowser;
  final Uri _tokenEndpoint;

  /// Trả về id_token của Google sau khi user đăng nhập thành công.
  ///
  /// Ném [AuthException] khi không mở được browser (EC-22), hết thời gian
  /// (EC-24) hoặc Google từ chối đổi code. Ném [GoogleSignInCanceledException]
  /// khi user chủ động từ chối trên trang Google (EC-04).
  Future<String> getIdToken() async {
    final Pkce pkce = Pkce.generate();
    final String state = _randomState();
    await _server.start();
    final String redirectUri = 'http://127.0.0.1:${_server.port}';

    final Uri authUrl = Uri.https('accounts.google.com', '/o/oauth2/v2/auth', <String, String>{
      'client_id': clientId,
      'redirect_uri': redirectUri,
      'response_type': 'code',
      'scope': 'openid email profile',
      'state': state,
      'code_challenge': pkce.challenge,
      'code_challenge_method': 'S256',
      'prompt': 'select_account',
    });

    try {
      await _openBrowser(authUrl);
    } on Exception {
      await _server.stop();
      throw const AuthException('Không mở được trình duyệt để đăng nhập');
    }

    final String code = await _server.waitForCode(expectedState: state);
    return _exchangeCodeForIdToken(code, redirectUri, pkce.verifier);
  }

  /// Đóng server nếu còn treo (flow bị hủy giữa chừng ở lớp trên).
  Future<void> dispose() => _server.stop();

  Future<String> _exchangeCodeForIdToken(
    String code,
    String redirectUri,
    String verifier,
  ) async {
    final Map<String, String> form = <String, String>{
      'code': code,
      'client_id': clientId,
      'redirect_uri': redirectUri,
      'grant_type': 'authorization_code',
      'code_verifier': verifier,
    };
    try {
      final Response<Map<String, dynamic>> response =
          await _dio.post<Map<String, dynamic>>(
        _tokenEndpoint.toString(),
        data: Uri(queryParameters: form).query, // form-urlencoded như Google yêu cầu
        options: Options(
          headers: <String, String>{'Content-Type': 'application/x-www-form-urlencoded'},
        ),
      );
      final dynamic idToken = response.data?['id_token'];
      if (idToken is! String || idToken.isEmpty) {
        throw const AuthException('Google không trả về id_token');
      }
      return idToken;
    } on AuthException {
      rethrow;
    } on DioException catch (e) {
      final dynamic payload = e.response?.data;
      final String? errorCode = payload is Map ? payload['error'] as String? : null;
      if (errorCode == 'access_denied') {
        throw const GoogleSignInCanceledException();
      }
      throw AuthException('Đổi token Google thất bại: ${e.type.name}');
    }
  }

  static String _randomState() {
    final Random rand = Random.secure();
    final List<String> values =
        List<String>.generate(32, (_) => _chars[rand.nextInt(_chars.length)]);
    return values.join();
  }

  static Future<void> _launchInBrowser(Uri url) async {
    final bool ok = await launchUrl(url, mode: LaunchMode.externalApplication);
    if (!ok) {
      throw const AuthException('Không mở được trình duyệt');
    }
  }
}
