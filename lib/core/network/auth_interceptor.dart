/// Interceptor gắn access token vào mọi request và tự refresh khi gặp 401.
///
/// - 401 → single-flight refresh (EC-31) → thử lại request gốc đúng 1 lần.
/// - Refresh fail vì phiên chết ([AuthException]) → báo onSessionExpired (EC-17).
/// - Refresh fail vì hạ tầng ([NetworkException]) → KHÔNG logout, giữ token (EC-16).
/// - Cờ isLoggingOut chặn refresh trong lúc đang logout (EC-33).
library;

import 'package:dio/dio.dart';

import '../error/exceptions.dart';
import 'session_refresher.dart';

class AuthInterceptor extends Interceptor {
  AuthInterceptor({
    required this.getAccessToken,
    required this.refresh,
    required this.onSessionExpired,
    required this.dio,
    SessionRefresher? refresher,
  }) : _refresher = refresher ?? SessionRefresher();

  final String? Function() getAccessToken;
  final Future<void> Function() refresh;
  final void Function() onSessionExpired;
  final Dio dio;
  final SessionRefresher _refresher;

  bool _isLoggingOut = false;

  /// Bật khi logout đang chạy để 401 ruột không kích hoạt refresh (EC-33).
  set isLoggingOut(bool value) => _isLoggingOut = value;

  @override
  void onRequest(RequestOptions options, RequestInterceptorHandler handler) {
    final String? token = getAccessToken();
    if (token != null && token.isNotEmpty) {
      options.headers['Authorization'] = 'Bearer $token';
    }
    handler.next(options);
  }

  @override
  void onError(DioException err, ErrorInterceptorHandler handler) async {
    final int? status = err.response?.statusCode;
    final String path = err.requestOptions.path;
    final bool isAuthEndpoint =
        path.contains('/auth/refresh') || path.contains('/auth/google');

    // Chỉ xử lý 401 từ API nghiệp vụ; endpoint auth tự xử lý ở tầng trên
    if (status != 401 || _isLoggingOut || isAuthEndpoint) {
      handler.next(err);
      return;
    }

    final RequestOptions options = err.requestOptions;
    if (options.extra['retried'] == true) {
      // Đã thử lại 1 lần mà vẫn 401 → không lặp vô hạn
      handler.next(err);
      return;
    }

    try {
      await _refresher.run(refresh);
    } on AuthException {
      onSessionExpired();
      handler.next(err);
      return;
    } on NetworkException {
      handler.next(err);
      return;
    } on Exception {
      handler.next(err);
      return;
    }

    // Refresh xong → thử lại request gốc với token mới
    final String? token = getAccessToken();
    options.headers['Authorization'] = 'Bearer $token';
    options.extra['retried'] = true;
    try {
      final Response<dynamic> response = await dio.fetch<dynamic>(options);
      handler.resolve(response);
    } on DioException catch (retryError) {
      handler.next(retryError);
    }
  }
}
