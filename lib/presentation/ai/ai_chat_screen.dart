import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../domain/entities/document_entities.dart';
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
    final List<ChatMessage> messages = ref.watch(chatMessagesProvider);
    final String? documentId = ref.watch(aiDocumentIdProvider);
    return Column(
      children: <Widget>[
        Padding(
          padding: const EdgeInsets.fromLTRB(24, 12, 24, 12),
          child: Column(
            children: <Widget>[
              const AiPageHeader(
                title: 'AI Chat',
                subtitle:
                    'Ask intelligent questions about the selected document.',
                icon: Icons.forum_outlined,
              ),
              const SizedBox(height: 16),
              AiDocumentPicker(
                documents: documents,
                value: documentId,
                onChanged: _busy
                    ? null
                    : (String? value) =>
                          ref.read(aiDocumentIdProvider.notifier).select(value),
              ),
            ],
          ),
        ),
        Expanded(
          child: ListView.builder(
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
                text: message.text,
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
        constraints: const BoxConstraints(maxWidth: 720),
        margin: const EdgeInsets.only(bottom: 12),
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
        decoration: BoxDecoration(
          color: fromUser ? colors.primary : colors.surfaceContainerHighest,
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
                  SizedBox(
                    width: 16,
                    height: 16,
                    child: CircularProgressIndicator(
                      strokeWidth: 2,
                      color: colors.primary,
                    ),
                  ),
                  const SizedBox(width: 10),
                  Text(text),
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
