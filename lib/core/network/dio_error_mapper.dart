/// Map DioException → exception nghiệp vụ để repository/repositoryImp xử lý thống nhất.
///
/// Quy tắc quan trọng (EC-16): lỗi hạ tầng (mạng/5xx/timeout) PHẢI là
/// [NetworkException] — không bao giờ map nhầm thành lỗi phiên để logout user.
library;

import 'package:dio/dio.dart';

import '../error/exceptions.dart';

String? extractDetail(Object? data) {
  if (data is Map) {
    final Object? detail = data['detail'];
    if (detail is String && detail.isNotEmpty) return detail;
  }
  return null;
}

Exception mapDioException(
  DioException e, {
  String fallback = 'Có lỗi xảy ra, thử lại sau',
}) {
  final int? code = e.response?.statusCode;
  if (code == 401 || code == 403) {
    return AuthException(
      extractDetail(e.response?.data) ?? 'Phiên đăng nhập không hợp lệ',
    );
  }
  if (code != null && code >= 500) {
    return const NetworkException('Máy chủ đang gặp sự cố, thử lại sau');
  }
  switch (e.type) {
    case DioExceptionType.connectionTimeout:
    case DioExceptionType.sendTimeout:
    case DioExceptionType.receiveTimeout:
    case DioExceptionType.connectionError:
      return const NetworkException();
    default:
      break;
  }
  return AuthException(extractDetail(e.response?.data) ?? fallback);
}
