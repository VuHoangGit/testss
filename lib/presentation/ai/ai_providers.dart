import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/capture/photo_capture.dart';
import '../../data/repositories/ai_chat_repository_impl.dart';
import '../../data/repositories/ai_repository_impl.dart';
import '../../domain/entities/chat_entities.dart';
import '../../domain/repositories/ai_chat_repository.dart';
import '../../domain/repositories/ai_repository.dart';
import '../providers.dart';

final Provider<AiRepository> aiRepositoryProvider = Provider<AiRepository>(
  (Ref ref) => AiRepositoryImpl(dio: ref.watch(apiDioProvider)),
);

/// Nguồn ảnh cho OCR (camera điện thoại / thư viện ảnh). Widget test override
/// bằng bản giả vì plugin camera không chạy được trong môi trường test.
final Provider<PhotoCapture> photoCaptureProvider = Provider<PhotoCapture>(
  (Ref ref) => const ImagePickerPhotoCapture(),
);

final Provider<AiChatRepository> aiChatRepositoryProvider =
    Provider<AiChatRepository>(
      (Ref ref) => AiChatRepositoryImpl(dio: ref.watch(apiDioProvider)),
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
    this.ocrPages = const <OcrPage>[],
    this.ocrWarnings = const <String>[],
    this.chatQuestion,
    this.chatAnswer,
    this.sourceText,
    this.translation,
  });

  final String? ocrText;
  final Map<String, String> ocrKeyValues;

  /// Nội dung từng trang + cảnh báo hậu kiểm của lượt OCR gần nhất.
  final List<OcrPage> ocrPages;
  final List<String> ocrWarnings;
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

  /// Lưu kết quả OCR (kèm nội dung từng trang và cảnh báo đối soát).
  void setOcrResult(OcrResult result) => state = LastAiResults(
    ocrText: result.text,
    ocrKeyValues: result.keyValues,
    ocrPages: result.pages,
    ocrWarnings: result.warnings,
  );

  void setOcr(String text, Map<String, String> keyValues) =>
      state = LastAiResults(ocrText: text, ocrKeyValues: keyValues);

  void setChat(String question, String answer) =>
      state = LastAiResults(chatQuestion: question, chatAnswer: answer);

  void setTranslation(String source, String translation) =>
      state = LastAiResults(sourceText: source, translation: translation);
}

/// Tin nhắn chat với AI — tách khỏi screen để voice cũng nối đoạn hội thoại.
/// Lịch sử được lưu phía backend theo tài liệu; đổi tài liệu → load lại.

class ChatHistoryState {
  const ChatHistoryState({
    this.documentId,
    this.conversationId,
    this.messages = const <ChatMessage>[],
    this.loading = false,
  });

  /// Tài liệu đang mở lịch sử — null = chưa gắn tài liệu nào.
  final String? documentId;

  /// Hội thoại trên server của tài liệu (null = chưa có hội thoại nào).
  final String? conversationId;
  final List<ChatMessage> messages;
  final bool loading;
}

final NotifierProvider<ChatMessagesController, ChatHistoryState>
chatMessagesProvider =
    NotifierProvider<ChatMessagesController, ChatHistoryState>(
      ChatMessagesController.new,
    );

class ChatMessagesController extends Notifier<ChatHistoryState> {
  @override
  ChatHistoryState build() => const ChatHistoryState();

  /// Tải hội thoại mới nhất của tài liệu; lỗi tải thì rỗng — không chặn chat mới.
  Future<void> loadForDocument(String documentId) async {
    if (state.documentId == documentId) return; // đang đúng tài liệu
    state = ChatHistoryState(documentId: documentId, loading: true);
    try {
      final AiChatRepository repo = ref.read(aiChatRepositoryProvider);
      final List<ChatConversation> conversations = await repo.conversations(
        documentId: documentId,
      );
      if (conversations.isEmpty) {
        state = ChatHistoryState(documentId: documentId);
        return;
      }
      final ChatConversation latest = conversations.first;
      final List<ChatMessage> history = await repo.messages(
        conversationId: latest.id,
      );
      state = ChatHistoryState(
        documentId: documentId,
        conversationId: latest.id,
        messages: history,
      );
    } on Exception {
      state = ChatHistoryState(documentId: documentId);
    }
  }

  void add(String text, {required bool fromUser}) => state = ChatHistoryState(
    documentId: state.documentId,
    conversationId: state.conversationId,
    messages: <ChatMessage>[
      ...state.messages,
      ChatMessage(role: fromUser ? 'user' : 'assistant', content: text),
    ],
  );

  void clear() => state = const ChatHistoryState();
}
