/// Hợp đồng tầng domain cho lịch sử hội thoại chat AI.
library;

import '../entities/chat_entities.dart';

abstract interface class AiChatRepository {
  /// Hội thoại của user, mới nhất trước; [documentId] để lọc theo tài liệu.
  Future<List<ChatConversation>> conversations({String? documentId});

  /// Tin nhắn của 1 hội thoại theo thứ tự gửi.
  Future<List<ChatMessage>> messages({required String conversationId});
}
