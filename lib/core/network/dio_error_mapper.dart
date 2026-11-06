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
  String fallback = 'Something went wrong, please try again later',
}) {
  final int? code = e.response?.statusCode;
  if (code == 402) {
    // Hết credit — không phải lỗi phiên: giữ nguyên detail hướng dẫn nạp
    return InsufficientCreditsException(
      extractDetail(e.response?.data) ?? 'Not enough credits to use AI features',
    );
  }
  if (code == 401 || code == 403) {
    return AuthException(
      extractDetail(e.response?.data) ?? 'Invalid session',
    );
  }
  if (code != null && code >= 500) {
    return const NetworkException('The server is having problems, please try again later');
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
