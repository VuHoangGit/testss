/// Cài đặt AiChatRepository qua API backend (dio có sẵn auth interceptor).
library;

import 'package:dio/dio.dart';

import '../../core/network/dio_error_mapper.dart';
import '../../domain/entities/chat_entities.dart';
import '../../domain/repositories/ai_chat_repository.dart';

class AiChatRepositoryImpl implements AiChatRepository {
  AiChatRepositoryImpl({required this.dio});

  final Dio dio;

  @override
  Future<List<ChatConversation>> conversations({String? documentId}) async {
    try {
      final Response<dynamic> response = await dio.get<dynamic>(
        '/ai/conversations',
        queryParameters: <String, dynamic>{'document_id': ?documentId},
      );
      final List<dynamic> rows = response.data as List<dynamic>;
      return <ChatConversation>[
        for (final dynamic row in rows)
          ChatConversation(
            id: row['id'] as String,
            title: row['title'] as String? ?? '',
            documentId: row['document_id'] as String?,
            updatedAt: DateTime.tryParse(row['updated_at'] as String? ?? ''),
          ),
      ];
    } on DioException catch (error) {
      throw mapDioException(
        error,
        fallback: 'Không tải được lịch sử hội thoại',
      );
    }
  }

  @override
  Future<List<ChatMessage>> messages({required String conversationId}) async {
    try {
      final Response<dynamic> response = await dio.get<dynamic>(
        '/ai/conversations/$conversationId/messages',
      );
      final List<dynamic> rows = response.data as List<dynamic>;
      return <ChatMessage>[
        for (final dynamic row in rows)
          ChatMessage(
            id: row['id'] as String,
            role: row['role'] as String,
            content: row['content'] as String,
            createdAt: DateTime.tryParse(row['created_at'] as String? ?? ''),
          ),
      ];
    } on DioException catch (error) {
      throw mapDioException(
        error,
        fallback: 'Không tải được tin nhắn hội thoại',
      );
    }
  }
}
