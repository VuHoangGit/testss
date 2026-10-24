import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../domain/repositories/ai_repository.dart';
import 'ai_providers.dart';
import 'ai_widgets.dart';

class AiTranslateScreen extends ConsumerStatefulWidget {
  const AiTranslateScreen({super.key});

  @override
  ConsumerState<AiTranslateScreen> createState() => _AiTranslateScreenState();
}

class _AiTranslateScreenState extends ConsumerState<AiTranslateScreen> {
  final TextEditingController _text = TextEditingController();
  bool _busy = false;

  @override
  void dispose() {
    _text.dispose();
    super.dispose();
  }

  Future<void> _translate() async {
    final String text = _text.text.trim();
    if (text.isEmpty) return;
    setState(() => _busy = true);
    try {
      final AiRepository ai = ref.read(aiRepositoryProvider);
      final String translation = await ai.translate(text);
      ref.read(lastAiResultsProvider.notifier).setTranslation(text, translation);
    } on Exception catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('$error')));
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final String? translation = ref.watch(lastAiResultsProvider).translation;
    return ListView(
      padding: const EdgeInsets.fromLTRB(24, 12, 24, 24),
      children: <Widget>[
        const AiPageHeader(
          title: 'Dịch vùng chọn',
          subtitle: 'Dán đoạn văn cần dịch và nhận bản dịch tự nhiên bằng AI.',
          icon: Icons.translate_outlined,
        ),
        const SizedBox(height: 24),
        TextField(
          controller: _text,
          minLines: 8,
          maxLines: 14,
          onChanged: (_) => setState(() {}),
          decoration: const InputDecoration(
            labelText: 'Nội dung cần dịch',
            hintText: 'Dán văn bản vào đây...',
            alignLabelWithHint: true,
            border: OutlineInputBorder(),
          ),
        ),
        const SizedBox(height: 12),
        FilledButton.icon(
          onPressed: _busy || _text.text.trim().isEmpty ? null : _translate,
          icon: const Icon(Icons.translate),
          label: const Text('Dịch sang English'),
        ),
        if (_busy) const Padding(
          padding: EdgeInsets.only(top: 20),
          child: LinearProgressIndicator(),
        ),
        if (translation != null) ...<Widget>[
          const SizedBox(height: 24),
          Text('Bản dịch', style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 8),
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: SelectableText(translation),
            ),
          ),
        ],
      ],
    );
  }
}
