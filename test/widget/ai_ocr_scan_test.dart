/// Widget test luồng "chụp ảnh điện thoại → OCR": ảnh phải được upload thành
/// tài liệu mới, được chọn ngay và OCR chạy trên đúng tài liệu đó.
library;

import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:docvaultproject/core/capture/photo_capture.dart';
import 'package:docvaultproject/domain/entities/document_entities.dart';
import 'package:docvaultproject/domain/repositories/ai_repository.dart';
import 'package:docvaultproject/presentation/ai/ai_ocr_screen.dart';
import 'package:docvaultproject/presentation/ai/ai_providers.dart';
import 'package:docvaultproject/presentation/documents/documents_controller.dart';
import 'package:docvaultproject/presentation/documents/documents_providers.dart';

/// PNG 1×1 hợp lệ — widget test không có camera và Image.memory cần bytes thật.
final Uint8List _onePixelPng = base64Decode(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwA'
  'EhQGAhKmMIQAAAABJRU5ErkJggg==',
);

class _FakePhotoCapture implements PhotoCapture {
  _FakePhotoCapture({this.photo});

  /// null = người dùng huỷ camera.
  final CapturedPhoto? photo;
  int takePhotoCalls = 0;
  int galleryCalls = 0;

  @override
  Future<CapturedPhoto?> takePhoto() async {
    takePhotoCalls++;
    return photo;
  }

  @override
  Future<CapturedPhoto?> pickFromGallery() async {
    galleryCalls++;
    return photo;
  }
}

class _FakeDocumentsController extends DocumentsController {
  String? uploadedFileName;
  Uint8List? uploadedBytes;

  @override
  Future<DocumentsState> build() async => const DocumentsState();

  @override
  Future<DocumentItem> uploadPhoto({
    required String fileName,
    required Uint8List bytes,
    void Function(int sent, int total)? onProgress,
  }) async {
    uploadedFileName = fileName;
    uploadedBytes = bytes;
    final DocumentItem document = DocumentItem(
      id: 'photo-1',
      name: fileName,
      mimeType: 'image/jpeg',
      sizeBytes: bytes.length,
      createdAt: DateTime(2026, 11, 22),
    );
    state = AsyncData(DocumentsState(documents: <DocumentItem>[document]));
    return document;
  }
}

class _FakeAiRepository implements AiRepository {
  String? ocrDocumentId;
  int ocrCalls = 0;

  @override
  Future<OcrResult> ocr(String documentId) async {
    ocrCalls++;
    ocrDocumentId = documentId;
    return const OcrResult(
      text: 'Số hợp đồng: 01/HĐ-2025',
      keyValues: <String, String>{'so_hieu': '01/HĐ-2025'},
      pages: <OcrPage>[
        OcrPage(page: 1, text: 'Số hợp đồng: 01/HĐ-2025'),
      ],
    );
  }

  @override
  Future<Uint8List> ocrWord(String documentId) async => Uint8List(0);

  @override
  Future<String> extractText(String documentId) async => '';

  @override
  Future<String> translate(
    String text, {
    String targetLanguage = 'English',
    String? sourceLanguage,
  }) async => '';

  @override
  Future<String> chat(String question, {required List<String> documentIds}) async =>
      '';

  @override
  Future<VoiceCommandResult> voiceCommand(
    String transcript, {
    required VoiceAppContext context,
    required String sessionId,
  }) async => const VoiceCommandResult(
    action: null,
    params: <String, dynamic>{},
    reply: '',
  );
}

Widget _screen({
  required _FakePhotoCapture photoCapture,
  required _FakeDocumentsController documents,
  required _FakeAiRepository ai,
}) => ProviderScope(
  overrides: [
    photoCaptureProvider.overrideWithValue(photoCapture),
    documentsControllerProvider.overrideWith(() => documents),
    aiRepositoryProvider.overrideWithValue(ai),
  ],
  child: const MaterialApp(home: Scaffold(body: AiOcrScreen())),
);

void main() {
  testWidgets('Bấm "Scan with camera" → upload ảnh thành tài liệu và OCR ngay', (
    WidgetTester tester,
  ) async {
    // Màn hình thật cao hơn 600px mặc định của test → đủ chỗ cho thẻ kết quả
    tester.view.physicalSize = const Size(1000, 1800);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final _FakePhotoCapture photoCapture = _FakePhotoCapture(
      photo: CapturedPhoto(
        bytes: _onePixelPng,
        fileName: 'scan_20261122_101530.jpg',
      ),
    );
    final _FakeDocumentsController documents = _FakeDocumentsController();
    final _FakeAiRepository ai = _FakeAiRepository();

    await tester.pumpWidget(
      _screen(photoCapture: photoCapture, documents: documents, ai: ai),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.text('Scan with camera'));
    await tester.pumpAndSettle();

    expect(photoCapture.takePhotoCalls, 1);
    expect(documents.uploadedFileName, 'scan_20261122_101530.jpg');
    expect(documents.uploadedBytes, _onePixelPng);
    // OCR chạy trên chính tài liệu vừa tạo từ ảnh, không phải tài liệu khác
    expect(ai.ocrCalls, 1);
    expect(ai.ocrDocumentId, 'photo-1');
    // Kết quả hiện ra ngay trên màn hình
    expect(find.text('Số hợp đồng: 01/HĐ-2025'), findsWidgets);
  });

  testWidgets('Huỷ camera → không upload, không gọi OCR', (
    WidgetTester tester,
  ) async {
    final _FakePhotoCapture photoCapture = _FakePhotoCapture();
    final _FakeDocumentsController documents = _FakeDocumentsController();
    final _FakeAiRepository ai = _FakeAiRepository();

    await tester.pumpWidget(
      _screen(photoCapture: photoCapture, documents: documents, ai: ai),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.text('Scan with camera'));
    await tester.pumpAndSettle();

    expect(photoCapture.takePhotoCalls, 1);
    expect(documents.uploadedFileName, isNull);
    expect(ai.ocrCalls, 0);
  });

  testWidgets('"Use a photo" đi qua thư viện ảnh, không mở camera', (
    WidgetTester tester,
  ) async {
    tester.view.physicalSize = const Size(1000, 1800);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final _FakePhotoCapture photoCapture = _FakePhotoCapture(
      photo: CapturedPhoto(bytes: _onePixelPng, fileName: 'scan_1.jpg'),
    );
    final _FakeAiRepository ai = _FakeAiRepository();

    await tester.pumpWidget(
      _screen(
        photoCapture: photoCapture,
        documents: _FakeDocumentsController(),
        ai: ai,
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.text('Use a photo'));
    await tester.pumpAndSettle();

    expect(photoCapture.galleryCalls, 1);
    expect(photoCapture.takePhotoCalls, 0);
    expect(ai.ocrCalls, 1);
  });
}
