import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../data/repositories/ai_repository_impl.dart';
import '../../domain/repositories/ai_repository.dart';
import '../providers.dart';

final Provider<AiRepository> aiRepositoryProvider = Provider<AiRepository>(
  (Ref ref) => AiRepositoryImpl(dio: ref.watch(apiDioProvider)),
);

/// Index công cụ trong tab AI: 0 OCR · 1 Chat · 2 Dịch.
final NotifierProvider<AiToolController, int> aiToolProvider =
    NotifierProvider<AiToolController, int>(AiToolController.new);

class AiToolController extends Notifier<int> {
  @override
  int build() => 1; // mặc định Chat (giữ hành vi trước khi refactor)

  void setTool(int index) {
    if (index >= 0 && index <= 2) {
      state = index;
    }
  }
}

/// Tài liệu PDF đang chọn cho các công cụ AI (OCR/Chat) — dùng chung giữa
/// screen và voice executor.
final NotifierProvider<SelectedAiDocument, String?> aiDocumentIdProvider =
    NotifierProvider<SelectedAiDocument, String?>(SelectedAiDocument.new);

class SelectedAiDocument extends Notifier<String?> {
  @override
  String? build() => null;

  void select(String? documentId) => state = documentId;
}

/// Kết quả AI gần nhất — để màn hình hiển thị và voice đọc lại (read_aloud).
class LastAiResults {
  const LastAiResults({
    this.ocrText,
    this.ocrKeyValues = const <String, String>{},
    this.chatQuestion,
    this.chatAnswer,
    this.sourceText,
    this.translation,
  });

  final String? ocrText;
  final Map<String, String> ocrKeyValues;
  final String? chatQuestion;
  final String? chatAnswer;
  final String? sourceText;
  final String? translation;
}

final NotifierProvider<LastAiResultsController, LastAiResults>
lastAiResultsProvider =
    NotifierProvider<LastAiResultsController, LastAiResults>(
      LastAiResultsController.new,
    );

class LastAiResultsController extends Notifier<LastAiResults> {
  @override
  LastAiResults build() => const LastAiResults();

  void setOcr(String text, Map<String, String> keyValues) =>
      state = LastAiResults(ocrText: text, ocrKeyValues: keyValues);

  void setChat(String question, String answer) => state = LastAiResults(
        chatQuestion: question,
        chatAnswer: answer,
      );

  void setTranslation(String source, String translation) =>
      state = LastAiResults(sourceText: source, translation: translation);
}

/// Tin nhắn chat với AI — tách khỏi screen để voice cũng nối đoạn hội thoại.
class ChatMessage {
  const ChatMessage({required this.text, required this.fromUser});

  final String text;
  final bool fromUser;
}

final NotifierProvider<ChatMessagesController, List<ChatMessage>>
chatMessagesProvider =
    NotifierProvider<ChatMessagesController, List<ChatMessage>>(
      ChatMessagesController.new,
    );

class ChatMessagesController extends Notifier<List<ChatMessage>> {
  @override
  List<ChatMessage> build() => <ChatMessage>[
        const ChatMessage(
          text:
              'Hello! Select a document and ask a question. I will answer based on its content.',
          fromUser: false,
        ),
      ];

  void add(String text, {required bool fromUser}) =>
      state = <ChatMessage>[...state, ChatMessage(text: text, fromUser: fromUser)];

  void clear() => state = <ChatMessage>[
        const ChatMessage(
          text:
              'Hello! Select a document and ask a question. I will answer based on its content.',
          fromUser: false,
        ),
      ];
}
