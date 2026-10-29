/// Entity hội thoại chat AI (lưu phía backend theo tài liệu).
library;

/// Một hội thoại chat gắn với tài liệu — mỗi lần chat vào cùng tài liệu sẽ
/// nối tiếp hội thoại mới nhất.
class ChatConversation {
  const ChatConversation({
    required this.id,
    required this.title,
    this.documentId,
    this.updatedAt,
  });

  final String id;
  final String title;
  final String? documentId;
  final DateTime? updatedAt;
}

/// Một tin nhắn trong hội thoại.
class ChatMessage {
  const ChatMessage({
    required this.role,
    required this.content,
    this.id,
    this.createdAt,
  });

  /// 'user' | 'assistant' — null id = tin vừa gửi phía client, chưa có bản ghi.
  final String role;
  final String content;
  final String? id;
  final DateTime? createdAt;

  bool get fromUser => role == 'user';
}
