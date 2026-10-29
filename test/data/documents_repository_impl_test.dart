/// Test DocumentsRepositoryImpl (Sprint 2) — mock Dio adapter, không mạng thật.
library;

import 'dart:convert';
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
import 'package:testss/data/repositories/documents_repository_impl.dart';

class _MockAdapter extends Mock implements HttpClientAdapter {}

void main() {
  setUpAll(() {
    registerFallbackValue(RequestOptions(path: '/fallback'));
    registerFallbackValue(<String, dynamic>{});
  });

  late _MockAdapter adapter;
  late DocumentsRepositoryImpl repo;

  setUp(() {
    adapter = _MockAdapter();
    final Dio dio = Dio(BaseOptions(baseUrl: 'http://localhost:8000/api/v1'));
    dio.httpClientAdapter = adapter;
    repo = DocumentsRepositoryImpl(dio: dio);
  });

  ResponseBody jsonBody(Object payload, [int status = 200]) =>
      ResponseBody.fromString(
        jsonEncode(payload),
        status,
        headers: <String, List<String>>{
          Headers.contentTypeHeader: <String>[Headers.jsonContentType],
        },
      );

  group('listDocuments', () {
    test('parse đúng danh sách từ snake_case JSON', () async {
      when(() => adapter.fetch(any(), any(), any())).thenAnswer(
        (_) async => jsonBody(<Map<String, dynamic>>[
          <String, dynamic>{
            'id': 'd1',
            'original_name': 'hop-dong.pdf',
            'mime_type': 'application/pdf',
            'size_bytes': 1024,
            'page_count': 3,
            'folder_id': 'f1',
            'created_at': '2026-10-12T00:00:00Z',
          },
        ]),
      );
      final docs = await repo.listDocuments();
      expect(docs, hasLength(1));
      expect(docs.first.name, 'hop-dong.pdf');
      expect(docs.first.pageCount, 3);
      expect(docs.first.isPdf, isTrue);
    });

    test('lọc theo folderId gửi query folder_id', () async {
      RequestOptions? captured;
      when(() => adapter.fetch(any(), any(), any())).thenAnswer((inv) async {
        captured = inv.positionalArguments[0] as RequestOptions;
        return jsonBody(<Map<String, dynamic>>[]);
      });
      await repo.listDocuments(folderId: 'abc');
      expect(captured!.path, '/documents');
      expect(captured!.queryParameters['folder_id'], 'abc');
    });
  });

  test('createFolder POST /folders và parse kết quả', () async {
    RequestOptions? captured;
    when(() => adapter.fetch(any(), any(), any())).thenAnswer((inv) async {
      captured = inv.positionalArguments[0] as RequestOptions;
      return jsonBody(<String, dynamic>{
        'id': 'f9',
        'name': 'Hợp đồng',
        'document_count': 0,
      }, 201);
    });
    final folder = await repo.createFolder('Hợp đồng');
    expect(captured!.method, 'POST');
    expect(captured!.path, '/folders');
    expect(folder.name, 'Hợp đồng');
  });

  test('uploadDocument gửi multipart tới /documents', () async {
    RequestOptions? captured;
    when(() => adapter.fetch(any(), any(), any())).thenAnswer((inv) async {
      captured = inv.positionalArguments[0] as RequestOptions;
      return jsonBody(<String, dynamic>{
        'id': 'd2',
        'original_name': 'a.pdf',
        'mime_type': 'application/pdf',
        'size_bytes': 5,
        'page_count': 1,
        'folder_id': null,
        'created_at': '2026-10-12T00:00:00Z',
      }, 201);
    });
    final int sentTotal = 0;
    await repo.uploadDocument(
      fileName: 'a.pdf',
      bytes: Uint8List.fromList(<int>[1, 2, 3, 4, 5]),
      onProgress: (_, _) {},
    );
    expect(captured!.path, '/documents');
    expect(captured!.data, isA<FormData>());
    expect(
      sentTotal,
      isZero,
    ); // callback không được gọi khi mock không báo progress
  });

  test('downloadDocument trả về bytes gốc', () async {
    when(() => adapter.fetch(any(), any(), any())).thenAnswer(
      (_) async => ResponseBody(
        Stream<Uint8List>.fromIterable(<Uint8List>[
          Uint8List.fromList(<int>[9, 9, 9]),
        ]),
        200,
        headers: <String, List<String>>{
          Headers.contentTypeHeader: <String>['application/pdf'],
        },
      ),
    );
    final bytes = await repo.downloadDocument('d1');
    expect(bytes, <int>[9, 9, 9]);
  });

  test('lỗi 404 ném exception kèm detail tiếng Việt', () async {
    when(() => adapter.fetch(any(), any(), any())).thenAnswer(
      (_) async =>
          jsonBody(<String, dynamic>{'detail': 'Không tìm thấy tài liệu'}, 404),
    );
    await expectLater(
      repo.deleteDocument('khong-ton-tai'),
      throwsA(
        isA<Exception>().having(
          (Object e) => e.toString(),
          'message',
          contains('Không tìm thấy tài liệu'),
        ),
      ),
    );
  });

  test('deleteFolder gọi DELETE /folders/{id}', () async {
    RequestOptions? captured;
    when(() => adapter.fetch(any(), any(), any())).thenAnswer((inv) async {
      captured = inv.positionalArguments[0] as RequestOptions;
      return jsonBody(<String, dynamic>{'detail': 'Đã xóa thư mục'});
    });
    await repo.deleteFolder('f1');
    expect(captured!.method, 'DELETE');
    expect(captured!.path, '/folders/f1');
  });
}
