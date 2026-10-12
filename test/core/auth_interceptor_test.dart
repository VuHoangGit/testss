import 'dart:convert';

import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
import 'package:testss/core/error/exceptions.dart';
import 'package:testss/core/network/auth_interceptor.dart';

class _MockAdapter extends Mock implements HttpClientAdapter {}

ResponseBody _body(int status, Map<String, dynamic> json) => ResponseBody.fromString(
      jsonEncode(json),
      status,
      headers: <String, List<String>>{
        Headers.contentTypeHeader: <String>['application/json'],
      },
    );

void main() {
  setUpAll(() {
    registerFallbackValue(RequestOptions(path: '/fallback'));
  });

  late Dio dio;
  late _MockAdapter adapter;
  late List<ResponseBody> queue;
  String? currentToken;
  int refreshCount = 0;
  int sessionExpiredCount = 0;

  setUp(() {
    dio = Dio(BaseOptions(baseUrl: 'http://localhost:8000'));
    adapter = _MockAdapter();
    dio.httpClientAdapter = adapter;
    queue = <ResponseBody>[];
    currentToken = 'old-token';
    refreshCount = 0;
    sessionExpiredCount = 0;

    when(() => adapter.fetch(any(), any(), any())).thenAnswer((Invocation _) async {
      if (queue.isEmpty) throw StateError('hết response trong queue');
      return queue.removeAt(0);
    });

    dio.interceptors.add(
      AuthInterceptor(
        dio: dio,
        getAccessToken: () => currentToken,
        refresh: () async {
          refreshCount++;
          // Độ trễ để 2 request song song cùng chạm refresh → kiểm chứng single-flight
          await Future<void>.delayed(const Duration(milliseconds: 40));
          currentToken = 'new-token';
        },
        onSessionExpired: () => sessionExpiredCount++,
      ),
    );
  });

  test('401 → refresh 1 lần → retry thành công với token mới', () async {
    queue.addAll(<ResponseBody>[
      _body(401, <String, dynamic>{'detail': 'hết hạn'}),
      _body(200, <String, dynamic>{'ok': true}),
    ]);

    final Response<dynamic> res = await dio.get<dynamic>('/things');
    expect((res.data as Map<String, dynamic>)['ok'], isTrue);
    expect(refreshCount, 1);
    expect(sessionExpiredCount, 0);
  });

  test('refresh nổ AuthException → onSessionExpired 1 lần, request trả 401', () async {
    dio.interceptors.clear();
    dio.interceptors.add(
      AuthInterceptor(
        dio: dio,
        getAccessToken: () => currentToken,
        refresh: () async => throw const AuthException('hết hạn'),
        onSessionExpired: () => sessionExpiredCount++,
      ),
    );
    queue.addAll(<ResponseBody>[_body(401, <String, dynamic>{})]);

    await expectLater(
      dio.get<dynamic>('/things'),
      throwsA(
        isA<DioException>().having(
          (DioException e) => e.response?.statusCode,
          'status',
          401,
        ),
      ),
    );
    expect(refreshCount, 0);
    expect(sessionExpiredCount, 1);
  });

  test('refresh nổ NetworkException → KHÔNG onSessionExpired (EC-16)', () async {
    dio.interceptors.clear();
    dio.interceptors.add(
      AuthInterceptor(
        dio: dio,
        getAccessToken: () => currentToken,
        refresh: () async => throw const NetworkException(),
        onSessionExpired: () => sessionExpiredCount++,
      ),
    );
    queue.addAll(<ResponseBody>[_body(401, <String, dynamic>{})]);

    await expectLater(dio.get<dynamic>('/things'), throwsA(isA<DioException>()));
    expect(sessionExpiredCount, 0);
  });

  test('2 request cùng dính 401 song song → chỉ 1 lần refresh (single-flight)', () async {
    queue.addAll(<ResponseBody>[
      _body(401, <String, dynamic>{}),
      _body(401, <String, dynamic>{}),
      _body(200, <String, dynamic>{'id': 1}),
      _body(200, <String, dynamic>{'id': 2}),
    ]);

    final List<Response<dynamic>> results =
        await Future.wait(<Future<Response<dynamic>>>[
      dio.get<dynamic>('/things'),
      dio.get<dynamic>('/things'),
    ]);
    expect(results.length, 2);
    expect(refreshCount, 1);
  });

  test('cờ isLoggingOut chặn refresh (EC-33)', () async {
    final AuthInterceptor interceptor =
        dio.interceptors.whereType<AuthInterceptor>().first;
    interceptor.isLoggingOut = true;
    queue.addAll(<ResponseBody>[_body(401, <String, dynamic>{})]);

    await expectLater(dio.get<dynamic>('/things'), throwsA(isA<DioException>()));
    expect(refreshCount, 0);
    expect(sessionExpiredCount, 0);
  });
}
