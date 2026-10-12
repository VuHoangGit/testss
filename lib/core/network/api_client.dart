/// Factory dựng Dio dùng chung cho cả app.
library;

import 'package:dio/dio.dart';

import '../config/app_config.dart';

Dio buildDio({
  String? baseUrl,
  List<Interceptor> interceptors = const <Interceptor>[],
}) {
  final Dio dio = Dio(
    BaseOptions(
      baseUrl: baseUrl ?? AppConfig.apiBaseUrl,
      connectTimeout: const Duration(seconds: 10),
      receiveTimeout: const Duration(seconds: 20),
      // Backend trả lỗi dạng {"detail": "..."} — để nguyên, tầng data tự map
      validateStatus: (int? code) => code != null && code >= 200 && code < 300,
    ),
  );
  dio.interceptors.addAll(interceptors);
  return dio;
}
