import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
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
          ..hideCurrentSnackBar()
          ..showSnackBar(SnackBar(content: Text('$error')));
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _runOcr(String documentId) => _run(() async {
    final AiRepository ai = ref.read(aiRepositoryProvider);
    final OcrResult result = await ai.ocr(documentId);
    ref.read(lastAiResultsProvider.notifier).setOcrResult(result);
  });

  Future<void> _exportWord(String documentId) => _run(() async {
    final AiRepository ai = ref.read(aiRepositoryProvider);
    final Uint8List bytes = await ai.ocrWord(documentId);
    await const FileSaver().saveBytes(
      fileName: 'ocr-result.docx',
      bytes: bytes,
      mimeType: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    );
  });

  Future<void> _copyText(String text) async {
    await Clipboard.setData(ClipboardData(text: text));
    if (mounted) {
      ScaffoldMessenger.of(context)
        ..hideCurrentSnackBar()
        ..showSnackBar(const SnackBar(content: Text('Copied to clipboard')));
    }
  }

  @override
  Widget build(BuildContext context) {
    final List<DocumentItem> documents =
        ref.watch(documentsControllerProvider).value?.documents ??
        const <DocumentItem>[];
    final String? documentId = ref.watch(aiDocumentIdProvider);
    final LastAiResults last = ref.watch(lastAiResultsProvider);
    final bool hasResult = last.ocrText != null;

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
              // Khi có kết quả, nút này đóng vai trò "Run again"
              onPressed: _busy || documentId == null
                  ? null
                  : () => _runOcr(documentId),
              icon: _busy
                  ? const SizedBox(
                      width: 16,
                      height: 16,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Icon(Icons.auto_awesome),
              label: Text(hasResult ? 'Run again' : 'Run OCR'),
            ),
            OutlinedButton.icon(
              onPressed: _busy || documentId == null
                  ? null
                  : () => _exportWord(documentId),
              icon: const Icon(Icons.download_outlined),
              label: const Text('Export Word'),
            ),
            if (hasResult && !_busy)
              OutlinedButton.icon(
                onPressed: () => _copyText(last.ocrText!),
                icon: const Icon(Icons.copy_rounded),
                label: const Text('Copy'),
              ),
          ],
        ),
        const SizedBox(height: 20),
        if (_busy)
          _ProcessingCard()
        else if (!hasResult)
          _OcrInitialCard()
        else
          _OcrResultCard(last: last),
      ],
    );
  }
}

/// Trạng thái 1 — chưa chạy OCR: hướng dẫn thao tác.
class _OcrInitialCard extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    final ColorScheme colors = Theme.of(context).colorScheme;
    return Card(
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 48, horizontal: 24),
        child: Column(
          children: <Widget>[
            Container(
              width: 56,
              height: 56,
              decoration: BoxDecoration(
                color: colors.primaryContainer,
                shape: BoxShape.circle,
              ),
              child: Icon(
                Icons.document_scanner_outlined,
                color: colors.primary,
                size: 26,
              ),
            ),
            const SizedBox(height: 14),
            Text(
              'No OCR result yet',
              style: Theme.of(context).textTheme.titleMedium,
            ),
            const SizedBox(height: 4),
            Text(
              'Select a PDF and tap "Run OCR" to extract its text and fields.',
              textAlign: TextAlign.center,
              style: Theme.of(context).textTheme.bodySmall,
            ),
          ],
        ),
      ),
    );
  }
}

/// Trạng thái 2 — đang xử lý.
class _ProcessingCard extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 48, horizontal: 24),
        child: Column(
          children: <Widget>[
            const CircularProgressIndicator(),
            const SizedBox(height: 16),
            Text(
              'Recognizing text…',
              style: Theme.of(context).textTheme.titleMedium,
            ),
            const SizedBox(height: 4),
            Text(
              'This usually takes a few seconds.',
              style: Theme.of(context).textTheme.bodySmall,
            ),
          ],
        ),
      ),
    );
  }
}

/// Trạng thái 3 — kết quả: tabs Preview text / Pages / Key-value fields.
class _OcrResultCard extends StatelessWidget {
  const _OcrResultCard({required this.last});

  final LastAiResults last;

  @override
  Widget build(BuildContext context) {
    final bool hasKeyValues = last.ocrKeyValues.isNotEmpty;
    final bool hasPages = last.ocrPages.length > 1;
    final int tabCount = 1 + (hasPages ? 1 : 0) + (hasKeyValues ? 1 : 0);
    return DefaultTabController(
      length: tabCount,
      child: Card(
        clipBehavior: Clip.antiAlias,
        child: Column(
          children: <Widget>[
            if (last.ocrWarnings.isNotEmpty)
              _OcrWarnings(warnings: last.ocrWarnings),
            TabBar(
              isScrollable: true,
              tabs: <Widget>[
                const Tab(text: 'Preview text'),
                if (hasPages) const Tab(text: 'Pages'),
                if (hasKeyValues) const Tab(text: 'Fields'),
              ],
            ),
            SizedBox(
              height: 360,
              child: TabBarView(
                children: <Widget>[
                  Scrollbar(
                    child: SingleChildScrollView(
                      padding: const EdgeInsets.all(16),
                      child: SelectableText(
                        last.ocrText ?? '',
                        style: Theme.of(context).textTheme.bodyMedium
                            ?.copyWith(height: 1.5),
                      ),
                    ),
                  ),
                  if (hasPages)
                    ListView.separated(
                      padding: const EdgeInsets.all(16),
                      itemCount: last.ocrPages.length,
                      separatorBuilder: (_, _) => const Divider(height: 1),
                      itemBuilder: (BuildContext context, int index) {
                        final OcrPage page = last.ocrPages[index];
                        return ExpansionTile(
                          tilePadding: EdgeInsets.zero,
                          title: Text('Page ${page.page}'),
                          subtitle: Text(
                            page.fromTextLayer
                                ? 'Text layer of the PDF'
                                : 'Read from the page image',
                            style: Theme.of(context).textTheme.bodySmall,
                          ),
                          children: <Widget>[
                            Padding(
                              padding: const EdgeInsets.only(bottom: 12),
                              child: SelectableText(
                                page.text,
                                style: Theme.of(context).textTheme.bodyMedium
                                    ?.copyWith(height: 1.5),
                              ),
                            ),
                          ],
                        );
                      },
                    ),
                  if (hasKeyValues)
                    ListView.separated(
                      padding: const EdgeInsets.all(16),
                      itemCount: last.ocrKeyValues.length,
                      separatorBuilder: (_, _) => const Divider(height: 1),
                      itemBuilder: (BuildContext context, int index) {
                        final MapEntry<String, String> entry = last
                            .ocrKeyValues
                            .entries
                            .elementAt(index);
                        return ListTile(
                          contentPadding: EdgeInsets.zero,
                          dense: true,
                          title: Text(
                            entry.key,
                            style: const TextStyle(fontWeight: FontWeight.w600),
                          ),
                          subtitle: Text(entry.value),
                        );
                      },
                    ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// Cảnh báo hậu kiểm — nhắc người dùng đối soát với ảnh trang gốc.
class _OcrWarnings extends StatelessWidget {
  const _OcrWarnings({required this.warnings});

  final List<String> warnings;

  @override
  Widget build(BuildContext context) {
    final ColorScheme colors = Theme.of(context).colorScheme;
    return Container(
      width: double.infinity,
      color: colors.tertiaryContainer,
      padding: const EdgeInsets.fromLTRB(16, 12, 16, 12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Row(
            children: <Widget>[
              Icon(Icons.error_outline, size: 18, color: colors.tertiary),
              const SizedBox(width: 8),
              Text(
                'Check these before using the result',
                style: Theme.of(context).textTheme.labelLarge?.copyWith(
                  color: colors.onTertiaryContainer,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ],
          ),
          const SizedBox(height: 6),
          for (final String warning in warnings)
            Padding(
              padding: const EdgeInsets.only(top: 2),
              child: Text(
                '• $warning',
                style: Theme.of(context).textTheme.bodySmall?.copyWith(
                  color: colors.onTertiaryContainer,
                ),
              ),
            ),
        ],
      ),
    );
  }
}
