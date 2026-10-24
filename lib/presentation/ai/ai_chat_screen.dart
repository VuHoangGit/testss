import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../domain/entities/document_entities.dart';
import '../../domain/repositories/ai_repository.dart';
import '../documents/documents_providers.dart';
import 'ai_providers.dart';
import 'ai_widgets.dart';

class _ChatMessage {
  const _ChatMessage({required this.text, required this.fromUser});

  final String text;
  final bool fromUser;
}

class AiChatScreen extends ConsumerStatefulWidget {
  const AiChatScreen({super.key});

  @override
  ConsumerState<AiChatScreen> createState() => _AiChatScreenState();
}

class _AiChatScreenState extends ConsumerState<AiChatScreen> {
  final TextEditingController _question = TextEditingController();
  final ScrollController _scroll = ScrollController();
  final List<_ChatMessage> _messages = <_ChatMessage>[
    const _ChatMessage(
      text: 'Xin chào! Hãy chọn một tài liệu và đặt câu hỏi, tôi sẽ trả lời dựa trên nội dung PDF đó.',
      fromUser: false,
    ),
  ];
  String? _documentId;
  bool _busy = false;

  @override
  void dispose() {
    _question.dispose();
    _scroll.dispose();
    super.dispose();
  }

  Future<void> _send() async {
    final String question = _question.text.trim();
    if (_busy || question.isEmpty || _documentId == null) return;
    _question.clear();
    setState(() {
      _messages.add(_ChatMessage(text: question, fromUser: true));
      _busy = true;
    });
    _scrollToBottom();
    try {
      final AiRepository ai = ref.read(aiRepositoryProvider);
      final String answer = await ai.chat(question, documentIds: <String>[_documentId!]);
      if (mounted) {
        setState(() => _messages.add(_ChatMessage(text: answer, fromUser: false)));
        _scrollToBottom();
      }
    } on Exception catch (error) {
      if (mounted) {
        setState(() => _messages.add(_ChatMessage(text: '$error', fromUser: false)));
      }
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
    return Column(
      children: <Widget>[
        Padding(
          padding: const EdgeInsets.fromLTRB(24, 12, 24, 12),
          child: Column(
            children: <Widget>[
              const AiPageHeader(
                title: 'Chat với AI',
                subtitle: 'Hỏi đáp thông minh theo nội dung tài liệu đã chọn.',
                icon: Icons.forum_outlined,
              ),
              const SizedBox(height: 16),
              AiDocumentPicker(
                documents: documents,
                value: _documentId,
                onChanged: _busy ? null : (String? value) => setState(() => _documentId = value),
              ),
            ],
          ),
        ),
        Expanded(
          child: ListView.builder(
            controller: _scroll,
            padding: const EdgeInsets.fromLTRB(24, 8, 24, 20),
            itemCount: _messages.length + (_busy ? 1 : 0),
            itemBuilder: (BuildContext context, int index) {
              if (_busy && index == _messages.length) {
                return const _ChatBubble(text: 'AI đang suy nghĩ...', fromUser: false, pending: true);
              }
              final _ChatMessage message = _messages[index];
              return _ChatBubble(text: message.text, fromUser: message.fromUser);
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
                  hintText: _documentId == null
                      ? 'Chọn tài liệu trước khi hỏi...'
                      : 'Nhập câu hỏi cho AI...',
                  border: InputBorder.none,
                  contentPadding: const EdgeInsets.symmetric(horizontal: 20, vertical: 14),
                  suffixIcon: IconButton(
                    onPressed: _question.text.trim().isEmpty || _documentId == null || _busy
                        ? null
                        : _send,
                    icon: const Icon(Icons.arrow_upward_rounded),
                    tooltip: 'Gửi câu hỏi',
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
                    child: CircularProgressIndicator(strokeWidth: 2, color: colors.primary),
                  ),
                  const SizedBox(width: 10),
                  Text(text),
                ],
              )
            : SelectableText(
                text,
                style: TextStyle(color: fromUser ? colors.onPrimary : colors.onSurface),
              ),
      ),
    );
  }
}
