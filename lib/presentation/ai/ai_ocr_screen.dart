import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/files/file_saver.dart';
import '../../domain/entities/document_entities.dart';
import '../../domain/repositories/ai_repository.dart';
import '../documents/documents_providers.dart';
import 'ai_providers.dart';
import 'ai_widgets.dart';

class AiOcrScreen extends ConsumerStatefulWidget {
  const AiOcrScreen({super.key});

  @override
  ConsumerState<AiOcrScreen> createState() => _AiOcrScreenState();
}

class _AiOcrScreenState extends ConsumerState<AiOcrScreen> {
  bool _busy = false;

  Future<void> _run(Future<void> Function() action) async {
    setState(() => _busy = true);
    try {
      await action();
    } on Exception catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('$error')));
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final List<DocumentItem> documents =
        ref.watch(documentsControllerProvider).value?.documents ??
        const <DocumentItem>[];
    final String? documentId = ref.watch(aiDocumentIdProvider);
    final LastAiResults last = ref.watch(lastAiResultsProvider);
    final AiRepository ai = ref.read(aiRepositoryProvider);
    return ListView(
      padding: const EdgeInsets.fromLTRB(24, 12, 24, 24),
      children: <Widget>[
        const AiPageHeader(
          title: 'OCR & Export to Word',
          subtitle: 'Extract content and data fields from a PDF.',
          icon: Icons.document_scanner_outlined,
        ),
        const SizedBox(height: 24),
        AiDocumentPicker(
          documents: documents,
          value: documentId,
          onChanged: _busy
              ? null
              : (String? value) =>
                    ref.read(aiDocumentIdProvider.notifier).select(value),
        ),
        const SizedBox(height: 12),
        Wrap(
          spacing: 10,
          runSpacing: 10,
          children: <Widget>[
            FilledButton.icon(
              onPressed: _busy || documentId == null
                  ? null
                  : () => _run(() async {
                      final OcrResult result = await ai.ocr(documentId);
                      ref
                          .read(lastAiResultsProvider.notifier)
                          .setOcr(result.text, result.keyValues);
                    }),
              icon: const Icon(Icons.auto_awesome),
              label: const Text('Run OCR'),
            ),
            OutlinedButton.icon(
              onPressed: _busy || documentId == null
                  ? null
                  : () => _run(() async {
                      final Uint8List bytes = await ai.ocrWord(documentId);
                      await const FileSaver().saveBytes(
                        fileName: 'ocr-result.docx',
                        bytes: bytes,
                        mimeType: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                      );
                    }),
              icon: const Icon(Icons.download_outlined),
              label: const Text('Export Word'),
            ),
          ],
        ),
        if (_busy)
          const Padding(
            padding: EdgeInsets.only(top: 20),
            child: LinearProgressIndicator(),
          ),
        if (last.ocrKeyValues.isNotEmpty) ...<Widget>[
          const SizedBox(height: 24),
          Text(
            'Extracted fields',
            style: Theme.of(context).textTheme.titleMedium,
          ),
          const SizedBox(height: 8),
          Card(
            child: Column(
              children: <Widget>[
                for (final MapEntry<String, String> entry
                    in last.ocrKeyValues.entries)
                  ListTile(title: Text(entry.key), subtitle: Text(entry.value)),
              ],
            ),
          ),
        ],
        if (last.ocrText != null) ...<Widget>[
          const SizedBox(height: 16),
          Text('OCR text', style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 8),
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: SelectableText(last.ocrText!),
            ),
          ),
        ],
      ],
    );
  }
}
