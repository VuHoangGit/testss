/// Interceptor gắn access token Supabase vào mọi request và refresh khi 401.
///
/// - 401 → gọi refresh của Supabase SDK (SDK tự lock nên nhiều request 401
///   cùng lúc không đá nhau) → thử lại request gốc đúng 1 lần.
/// - Refresh fail vì phiên chết ([AuthException]) → báo onSessionExpired.
/// - Refresh fail vì hạ tầng ([NetworkException]/lỗi khác) → KHÔNG logout,
///   giữ phiên (tab background lâu ngày thường gặp).
library;

import 'package:dio/dio.dart';

import '../error/exceptions.dart';

class AuthInterceptor extends Interceptor {
  AuthInterceptor({
    required this.getAccessToken,
    required this.refresh,
    required this.onSessionExpired,
    required this.dio,
  });

  final String? Function() getAccessToken;
  final Future<void> Function() refresh;
  final void Function() onSessionExpired;
  final Dio dio;

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
    // Chỉ xử lý 401 và chưa thử lại lần nào (chặn lặp vô hạn)
    if (status != 401 || err.requestOptions.extra['retried'] == true) {
      handler.next(err);
      return;
    }
    try {
      await refresh();
    } on AuthException {
      onSessionExpired();
      handler.next(err);
      return;
    } on Exception {
      // Lỗi hạ tầng khi refresh — không logout, đẩy lỗi gốc lên tầng trên
      handler.next(err);
      return;
    }

    // Refresh xong → thử lại request gốc với token mới
    final String? token = getAccessToken();
    err.requestOptions.headers['Authorization'] = 'Bearer $token';
    err.requestOptions.extra['retried'] = true;
    try {
      final Response<dynamic> response = await dio.fetch<dynamic>(
        err.requestOptions,
      );
      handler.resolve(response);
    } on DioException catch (retryError) {
      handler.next(retryError);
    }
  }
}
