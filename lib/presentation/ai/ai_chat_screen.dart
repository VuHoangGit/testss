import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../domain/entities/document_entities.dart';
import '../../domain/entities/chat_entities.dart';
import '../../domain/repositories/ai_repository.dart';
import '../documents/documents_providers.dart';
import 'ai_providers.dart';
import 'ai_widgets.dart';

class AiChatScreen extends ConsumerStatefulWidget {
  const AiChatScreen({super.key});

  @override
  ConsumerState<AiChatScreen> createState() => _AiChatScreenState();
}

class _AiChatScreenState extends ConsumerState<AiChatScreen> {
  final TextEditingController _question = TextEditingController();
  final ScrollController _scroll = ScrollController();
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    // Document có thể đã được chọn từ trước (voice/dashboard) — tải luôn lịch sử
    final String? documentId = ref.read(aiDocumentIdProvider);
    if (documentId != null) {
      ref.read(chatMessagesProvider.notifier).loadForDocument(documentId);
    }
  }

  @override
  void dispose() {
    _question.dispose();
    _scroll.dispose();
    super.dispose();
  }

  Future<void> _send() async {
    final String question = _question.text.trim();
    final String? documentId = ref.read(aiDocumentIdProvider);
    if (_busy || question.isEmpty || documentId == null) return;
    _question.clear();
    setState(() => _busy = true);
    final ChatMessagesController messages = ref.read(
      chatMessagesProvider.notifier,
    );
    messages.add(question, fromUser: true);
    _scrollToBottom();
    try {
      final AiRepository ai = ref.read(aiRepositoryProvider);
      final String answer = await ai.chat(
        question,
        documentIds: <String>[documentId],
      );
      messages.add(answer, fromUser: false);
      ref.read(lastAiResultsProvider.notifier).setChat(question, answer);
      _scrollToBottom();
    } on Exception catch (error) {
      messages.add('$error', fromUser: false);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  void _scrollToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scroll.hasClients) {
        _scroll.animateTo(
          _scroll.position.maxScrollExtent,
          duration: const Duration(milliseconds: 250),
          curve: Curves.easeOut,
        );
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    final List<DocumentItem> documents =
        ref.watch(documentsControllerProvider).value?.documents ??
        const <DocumentItem>[];
    final ChatHistoryState history = ref.watch(chatMessagesProvider);
    final List<ChatMessage> messages = history.messages;
    final String? documentId = ref.watch(aiDocumentIdProvider);
    // Đổi tài liệu → tải lại lịch sử hội thoại của tài liệu đó
    ref.listen<String?>(aiDocumentIdProvider, (_, String? next) {
      if (next != null) {
        ref.read(chatMessagesProvider.notifier).loadForDocument(next);
      }
    });
    // Viewport thực rất thấp (IndexedStack lồng trong shell + AI Center,
    // hoặc mobile landscape): ẩn header trang — AI Center phía trên đã có
    // tên công cụ; tránh RenderFlex overflow.
    return LayoutBuilder(
      builder: (BuildContext context, BoxConstraints constraints) {
        final bool tight = constraints.maxHeight < 240;
        return Column(
          children: <Widget>[
            Padding(
              padding: EdgeInsets.fromLTRB(
                24,
                tight ? 8 : 12,
                24,
                tight ? 8 : 12,
              ),
              child: Column(
                children: <Widget>[
                  if (!tight)
                    const AiPageHeader(
                      title: 'AI Chat',
                      subtitle: 'Ask intelligent questions about the selected document.',
                      icon: Icons.forum_outlined,
                    ),
                  SizedBox(height: tight ? 0 : 16),
                  AiDocumentPicker(
                    documents: documents,
                    value: documentId,
                    onChanged: _busy
                        ? null
                        : (String? value) => ref
                              .read(aiDocumentIdProvider.notifier)
                              .select(value),
                  ),
                ],
              ),
            ),
            Expanded(
              child: history.loading
                  ? const Center(child: CircularProgressIndicator())
                  : messages.isEmpty
                  ? _ChatEmptyState(
                      documentId: documentId,
                      onPrompt: (String prompt) {
                        // Điền gợi ý vào ô nhập để người dùng xem/sửa rồi gửi
                        _question.text = prompt;
                        setState(() {});
                      },
                    )
                  : ListView.builder(
                      controller: _scroll,
                      padding: const EdgeInsets.fromLTRB(24, 8, 24, 20),
                      itemCount: messages.length + (_busy ? 1 : 0),
                      itemBuilder: (BuildContext context, int index) {
                        if (_busy && index == messages.length) {
                          return const _ChatBubble(
                            text: 'AI is thinking...',
                            fromUser: false,
                            pending: true,
                          );
                        }
                        final ChatMessage message = messages[index];
                        return _ChatBubble(
                          text: message.content,
                          fromUser: message.fromUser,
                        );
                      },
                    ),
            ),
            SafeArea(
              top: false,
              child: Padding(
                padding: const EdgeInsets.fromLTRB(16, 8, 16, 12),
                child: Material(
                  elevation: 3,
                  borderRadius: BorderRadius.circular(28),
                  color: Theme.of(context).colorScheme.surfaceContainerHighest,
                  child: TextField(
                    controller: _question,
                    minLines: 1,
                    maxLines: 5,
                    onChanged: (_) => setState(() {}),
                    onSubmitted: (_) => _send(),
                    decoration: InputDecoration(
                      hintText: documentId == null
                          ? 'Select a document before asking...'
                          : 'Ask AI a question...',
                      border: InputBorder.none,
                      contentPadding: const EdgeInsets.symmetric(
                        horizontal: 20,
                        vertical: 14,
                      ),
                      suffixIcon: IconButton(
                        onPressed:
                            _question.text.trim().isEmpty ||
                                documentId == null ||
                                _busy
                            ? null
                            : _send,
                        icon: const Icon(Icons.arrow_upward_rounded),
                        tooltip: 'Send question',
                      ),
                    ),
                  ),
                ),
              ),
            ),
          ],
        );
      },
    );
  }
}

class _ChatBubble extends StatelessWidget {
  const _ChatBubble({
    required this.text,
    required this.fromUser,
    this.pending = false,
  });

  final String text;
  final bool fromUser;
  final bool pending;

  @override
  Widget build(BuildContext context) {
    final ColorScheme colors = Theme.of(context).colorScheme;
    return Align(
      alignment: fromUser ? Alignment.centerRight : Alignment.centerLeft,
      child: Container(
        // Spec: bong bóng chat tối đa ~70% bề ngang
        constraints: BoxConstraints(
          maxWidth: MediaQuery.sizeOf(context).width * 0.7,
        ),
        margin: const EdgeInsets.only(bottom: 12),
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
        decoration: BoxDecoration(
          color: fromUser ? colors.primary : colors.surface,
          border: fromUser ? null : Border.all(color: colors.outlineVariant),
          borderRadius: BorderRadius.only(
            topLeft: const Radius.circular(18),
            topRight: const Radius.circular(18),
            bottomLeft: Radius.circular(fromUser ? 18 : 4),
            bottomRight: Radius.circular(fromUser ? 4 : 18),
          ),
        ),
        child: pending
            ? Row(
                mainAxisSize: MainAxisSize.min,
                children: <Widget>[
                  const _TypingDots(),
                  const SizedBox(width: 10),
                  Text(text, style: Theme.of(context).textTheme.bodyMedium),
                ],
              )
            : SelectableText(
                text,
                style: TextStyle(
                  color: fromUser ? colors.onPrimary : colors.onSurface,
                ),
              ),
      ),
    );
  }
}

/// 3 chấm "AI đang gõ" — nhấp nháy tuần tự.
class _TypingDots extends StatefulWidget {
  const _TypingDots();

  @override
  State<_TypingDots> createState() => _TypingDotsState();
}

class _TypingDotsState extends State<_TypingDots>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller = AnimationController(
    vsync: this,
    duration: const Duration(milliseconds: 900),
  )..repeat();

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final Color color = Theme.of(context).colorScheme.primary;
    return AnimatedBuilder(
      animation: _controller,
      builder: (BuildContext context, _) {
        return Row(
          mainAxisSize: MainAxisSize.min,
          children: List<Widget>.generate(3, (int i) {
            final double t = (_controller.value * 3 - i) % 1.0;
            final double opacity = 0.3 + 0.7 * (t < 0 ? t + 1 : t);
            return Padding(
              padding: const EdgeInsets.symmetric(horizontal: 2),
              child: Container(
                width: 6,
                height: 6,
                decoration: BoxDecoration(
                  color: color.withValues(alpha: opacity.clamp(0.3, 1.0)),
                  shape: BoxShape.circle,
                ),
              ),
            );
          }),
        );
      },
    );
  }
}

/// Trạng thái rỗng của khung chat: chưa chọn tài liệu / chưa có tin nhắn.
/// Khi đã chọn tài liệu, gợi ý 4 câu hỏi mẫu điền sẵn vào ô nhập.
class _ChatEmptyState extends StatelessWidget {
  const _ChatEmptyState({required this.documentId, required this.onPrompt});

  final String? documentId;
  final ValueChanged<String> onPrompt;

  static const List<String> _prompts = <String>[
    'Summarize this document in a few sentences',
    'What are the key points I should know?',
    'List all important dates and deadlines',
    'Which clauses mention payment terms?',
  ];

  @override
  Widget build(BuildContext context) {
    final ColorScheme colors = Theme.of(context).colorScheme;
    final bool hasDoc = documentId != null;
    return Center(
      child: SingleChildScrollView(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            Container(
              width: 56,
              height: 56,
              decoration: BoxDecoration(
                color: colors.primaryContainer,
                shape: BoxShape.circle,
              ),
              child: Icon(
                hasDoc ? Icons.forum_outlined : Icons.folder_open_rounded,
                color: colors.primary,
                size: 26,
              ),
            ),
            const SizedBox(height: 14),
            Text(
              hasDoc
                  ? 'No messages yet — ask the first question.'
                  : 'Select a document to see chat history.',
              style: Theme.of(context).textTheme.titleMedium,
            ),
            if (hasDoc) ...<Widget>[
              const SizedBox(height: 20),
              Wrap(
                spacing: 8,
                runSpacing: 8,
                alignment: WrapAlignment.center,
                children: <Widget>[
                  for (final String prompt in _prompts)
                    ActionChip(
                      label: Text(prompt),
                      onPressed: () => onPrompt(prompt),
                    ),
                ],
              ),
            ],
          ],
        ),
      ),
    );
  }
}
