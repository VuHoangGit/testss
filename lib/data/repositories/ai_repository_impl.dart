import 'dart:typed_data';

import 'package:dio/dio.dart';

import '../../core/error/exceptions.dart';
import '../../core/network/dio_error_mapper.dart';
import '../../domain/repositories/ai_repository.dart';

/// Map lỗi gọi AI. Server trả 503 kèm `detail` tiếng Việt cho lỗi AI
/// (vd "Không đọc được trang nào của tài liệu.") — hiện đúng câu đó thay vì
/// câu chung "server đang có vấn đề". Vẫn dùng [NetworkException] để không
/// bao giờ bị hiểu nhầm thành lỗi phiên (EC-16).
Exception _mapAiError(DioException error, String fallback) {
  final int? status = error.response?.statusCode;
  final String? detail = extractDetail(error.response?.data);
  if (status != null && status >= 500 && detail != null) {
    return NetworkException(detail);
  }
  return mapDioException(error, fallback: fallback);
}

class AiRepositoryImpl implements AiRepository {
  AiRepositoryImpl({required this.dio});

  final Dio dio;

  @override
  Future<OcrResult> ocr(String documentId) async {
    try {
      final Response<dynamic> response = await dio.post<dynamic>(
        '/ai/ocr/$documentId',
      );
      final Map<String, dynamic> data = response.data as Map<String, dynamic>;
      final List<dynamic> pages = data['pages'] as List<dynamic>? ?? <dynamic>[];
      final List<dynamic> warnings =
          data['warnings'] as List<dynamic>? ?? <dynamic>[];
      return OcrResult(
        text: data['text'] as String,
        keyValues: (data['key_values'] as Map<dynamic, dynamic>).map(
          (dynamic key, dynamic value) =>
              MapEntry(key.toString(), value.toString()),
        ),
        pages: <OcrPage>[
          for (final dynamic page in pages)
            OcrPage(
              page: page['page'] as int,
              text: page['text'] as String? ?? '',
              // server: "text-layer" = chữ có sẵn trong PDF, "vision" = AI đọc ảnh
              fromTextLayer: page['source'] == 'text-layer',
            ),
        ],
        warnings: <String>[for (final dynamic w in warnings) w.toString()],
      );
    } on DioException catch (error) {
      throw _mapAiError(error, 'Could not run OCR on the document');
    }
  }

  @override
  Future<Uint8List> ocrWord(String documentId) async {
    try {
      final Response<List<int>> response = await dio.post<List<int>>(
        '/ai/ocr/$documentId/word',
        options: Options(responseType: ResponseType.bytes),
      );
      return Uint8List.fromList(response.data ?? <int>[]);
    } on DioException catch (error) {
      throw _mapAiError(error, 'Could not export to Word');
    }
  }

  @override
  Future<String> extractText(String documentId) async {
    try {
      final Response<dynamic> response = await dio.get<dynamic>(
        '/ai/extract-text/$documentId',
      );
      return (response.data as Map<String, dynamic>)['text'] as String;
    } on DioException catch (error) {
      throw mapDioException(
        error,
        fallback: 'Could not read the document content',
      );
    }
  }

  @override
  Future<String> translate(
    String text, {
    String targetLanguage = 'English',
    String? sourceLanguage,
  }) async {
    try {
      final Response<dynamic> response = await dio.post<dynamic>(
        '/ai/translate',
        data: <String, dynamic>{
          'text': text,
          'target_language': targetLanguage,
          if (sourceLanguage != null && sourceLanguage.trim().isNotEmpty)
            'source_language': sourceLanguage.trim(),
        },
      );
      return (response.data as Map<String, dynamic>)['translation'] as String;
    } on DioException catch (error) {
      throw mapDioException(error, fallback: 'Could not translate the text');
    }
  }

  @override
  Future<String> chat(
    String question, {
    required List<String> documentIds,
  }) async {
    try {
      final Response<dynamic> response = await dio.post<dynamic>(
        '/ai/chat',
        data: <String, dynamic>{
          'question': question,
          'document_ids': documentIds,
        },
      );
      return (response.data as Map<String, dynamic>)['answer'] as String;
    } on DioException catch (error) {
      throw _mapAiError(error, 'Could not get an answer from the AI');
    }
  }

  @override
  Future<VoiceCommandResult> voiceCommand(
    String transcript, {
    required VoiceAppContext context,
    required String sessionId,
  }) async {
    try {
      final Response<dynamic> response = await dio.post<dynamic>(
        '/ai/voice-command',
        data: <String, dynamic>{
          'transcript': transcript,
          'session_id': sessionId,
          'context': <String, dynamic>{
            'current_tab': context.currentTab,
            'folders': <Map<String, String>>[
              for (final VoiceFolderRef folder in context.folders)
                <String, String>{'id': folder.id, 'name': folder.name},
            ],
            'documents': <Map<String, String>>[
              for (final VoiceDocumentRef document in context.documents)
                <String, String>{
                  'id': document.id,
                  'name': document.name,
                  'mime_type': document.mimeType,
                },
            ],
          },
        },
      );
      final Map<String, dynamic> data = response.data as Map<String, dynamic>;
      return VoiceCommandResult(
        action: data['action'] as String?,
        params:
            (data['params'] as Map<dynamic, dynamic>?)?.map(
              (dynamic key, dynamic value) => MapEntry(key.toString(), value),
            ) ??
            <String, dynamic>{},
        reply: data['reply'] as String,
      );
    } on DioException catch (error) {
      throw mapDioException(
        error,
        fallback: 'Could not interpret the voice command',
      );
    }
  }
}
