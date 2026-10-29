/// Widget test màn AI Chat: tải lịch sử hội thoại theo tài liệu + nối tin mới.
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:testss/domain/entities/chat_entities.dart';
import 'package:testss/domain/entities/document_entities.dart';
import 'package:testss/domain/repositories/ai_chat_repository.dart';
import 'package:testss/presentation/ai/ai_providers.dart';
import 'package:testss/presentation/ai/ai_chat_screen.dart';
import 'package:testss/presentation/documents/documents_controller.dart';
import 'package:testss/presentation/documents/documents_providers.dart';

class _FakeAiChatRepository implements AiChatRepository {
  _FakeAiChatRepository(this._messages);

  final List<ChatMessage> _messages;
  int messagesCalls = 0;

  @override
  Future<List<ChatConversation>> conversations({String? documentId}) async =>
      <ChatConversation>[
        ChatConversation(id: 'conv-1', title: 'Câu cũ', documentId: documentId),
      ];

  @override
  Future<List<ChatMessage>> messages({required String conversationId}) async {
    messagesCalls++;
    return _messages;
  }
}

class _FakeDocumentsController extends DocumentsController {
  @override
  Future<DocumentsState> build() async => DocumentsState(
    documents: <DocumentItem>[
      DocumentItem(
        id: 'doc-1',
        name: 'hop-dong.pdf',
        mimeType: 'application/pdf',
        sizeBytes: 10,
        createdAt: DateTime(2026, 10, 1),
      ),
    ],
  );
}

void main() {
  testWidgets('Chọn tài liệu → hiện lịch sử hội thoại đã lưu', (
    WidgetTester tester,
  ) async {
    final _FakeAiChatRepository repo = _FakeAiChatRepository(<ChatMessage>[
      const ChatMessage(
        id: 'm1',
        role: 'user',
        content: 'Hợp đồng có hiệu lực khi nào?',
      ),
      const ChatMessage(
        id: 'm2',
        role: 'assistant',
        content: 'Từ ngày 01/10/2026.',
      ),
    ]);

    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          aiChatRepositoryProvider.overrideWithValue(repo),
          documentsControllerProvider.overrideWith(
            _FakeDocumentsController.new,
          ),
        ],
        child: const MaterialApp(home: Scaffold(body: AiChatScreen())),
      ),
    );
    await tester.pumpAndSettle();

    // Chưa chọn tài liệu → placeholder, chưa gọi API history
    expect(find.text('Select a document to see chat history.'), findsOneWidget);
    expect(repo.messagesCalls, 0);

    // Chọn tài liệu trong picker → tải lịch sử
    await tester.tap(find.byType(DropdownButtonFormField<String>));
    await tester.pumpAndSettle();
    await tester.tap(find.text('hop-dong.pdf').last);
    await tester.pumpAndSettle();

    expect(repo.messagesCalls, 1);
    expect(find.text('Hợp đồng có hiệu lực khi nào?'), findsOneWidget);
    expect(find.text('Từ ngày 01/10/2026.'), findsOneWidget);
  });

  testWidgets('Tài liệu chưa có hội thoại → gợi ý hỏi câu đầu', (
    WidgetTester tester,
  ) async {
    final _FakeAiChatRepository repo = _FakeAiChatRepository(
      const <ChatMessage>[],
    );

    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          aiChatRepositoryProvider.overrideWithValue(repo),
          documentsControllerProvider.overrideWith(
            _FakeDocumentsController.new,
          ),
        ],
        child: const MaterialApp(home: Scaffold(body: AiChatScreen())),
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.byType(DropdownButtonFormField<String>));
    await tester.pumpAndSettle();
    await tester.tap(find.text('hop-dong.pdf').last);
    await tester.pumpAndSettle();

    // conversations trả về 1 hội thoại nhưng rỗng tin nhắn — vẫn hiện gợi ý
    expect(
      find.text('No messages yet — ask the first question.'),
      findsOneWidget,
    );
  });
}
