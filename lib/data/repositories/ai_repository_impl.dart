import 'dart:typed_data';

import 'package:dio/dio.dart';

import '../../core/network/dio_error_mapper.dart';
import '../../domain/repositories/ai_repository.dart';

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
      return OcrResult(
        text: data['text'] as String,
        keyValues: (data['key_values'] as Map<dynamic, dynamic>).map(
          (dynamic key, dynamic value) =>
              MapEntry(key.toString(), value.toString()),
        ),
      );
    } on DioException catch (error) {
      throw mapDioException(error, fallback: 'Không OCR được tài liệu');
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
      throw mapDioException(error, fallback: 'Không xuất được Word');
    }
  }

  @override
  Future<String> translate(
    String text, {
    String targetLanguage = 'English',
  }) async {
    try {
      final Response<dynamic> response = await dio.post<dynamic>(
        '/ai/translate',
        data: <String, String>{'text': text, 'target_language': targetLanguage},
      );
      return (response.data as Map<String, dynamic>)['translation'] as String;
    } on DioException catch (error) {
      throw mapDioException(error, fallback: 'Không dịch được đoạn văn');
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
      throw mapDioException(error, fallback: 'Không nhận được câu trả lời AI');
    }
  }
}
