/// Test AiRepositoryImpl.ocr — parse payload OCR mới (pages + warnings).
library;

import 'dart:convert';

import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
import 'package:testss/data/repositories/ai_repository_impl.dart';
import 'package:testss/domain/repositories/ai_repository.dart';

class _MockAdapter extends Mock implements HttpClientAdapter {}

void main() {
  setUpAll(() {
    registerFallbackValue(RequestOptions(path: '/fallback'));
  });

  late _MockAdapter adapter;
  late AiRepositoryImpl repo;

  setUp(() {
    adapter = _MockAdapter();
    final Dio dio = Dio(BaseOptions(baseUrl: 'http://localhost:8000/api/v1'));
    dio.httpClientAdapter = adapter;
    repo = AiRepositoryImpl(dio: dio);
  });

  ResponseBody jsonBody(Object payload, [int status = 200]) =>
      ResponseBody.fromString(
        jsonEncode(payload),
        status,
        headers: <String, List<String>>{
          Headers.contentTypeHeader: <String>[Headers.jsonContentType],
        },
      );

  test('parse text, key_values, pages và warnings', () async {
    when(
      () => adapter.fetch(any(), any(), any()),
    ).thenAnswer(
      (_) async => jsonBody(<String, dynamic>{
        'text': '--- Trang 1 ---\nHợp đồng\n\n--- Trang 2 ---\nĐiều 2',
        'key_values': <String, String>{'so_hieu': '01/HĐ'},
        'pages': <Map<String, dynamic>>[
          <String, dynamic>{
            'page': 1,
            'text': 'Hợp đồng',
            'source': 'text-layer',
          },
          <String, dynamic>{
            'page': 2,
            'text': 'Điều 2',
            'source': 'vision',
          },
        ],
        'warnings': <String>['Có 1 chỗ AI đánh dấu không đọc được ([?]/[mất chữ])'],
      }),
    );

    final OcrResult result = await repo.ocr('doc-1');

    expect(result.keyValues['so_hieu'], '01/HĐ');
    expect(result.pages, hasLength(2));
    expect(result.pages.first.page, 1);
    expect(result.pages.first.text, 'Hợp đồng');
    expect(result.pages.first.fromTextLayer, isTrue);
    expect(result.pages.last.fromTextLayer, isFalse);
    expect(result.warnings, hasLength(1));
  });

  test('server cũ không trả pages/warnings → vẫn parse được', () async {
    when(
      () => adapter.fetch(any(), any(), any()),
    ).thenAnswer(
      (_) async => jsonBody(<String, dynamic>{
        'text': 'Nội dung',
        'key_values': <String, String>{'so_hieu': '02/HĐ'},
      }),
    );

    final OcrResult result = await repo.ocr('doc-1');

    expect(result.text, 'Nội dung');
    expect(result.pages, isEmpty);
    expect(result.warnings, isEmpty);
  });

  test('lỗi 503 từ AI → message thân thiện', () async {
    when(
      () => adapter.fetch(any(), any(), any()),
    ).thenAnswer(
      (_) async => jsonBody(<String, dynamic>{
        'detail': 'Không đọc được trang nào của tài liệu.',
      }, 503),
    );

    expect(
      () => repo.ocr('doc-1'),
      throwsA(
        predicate(
          (Object error) =>
              error.toString().contains('Không đọc được trang nào'),
        ),
      ),
    );
  });
}
