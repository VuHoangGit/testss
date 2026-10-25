import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart' show SelectedContent;
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../domain/entities/document_entities.dart';
import '../documents/documents_providers.dart';
import 'ai_providers.dart';
import 'ai_widgets.dart';

/// Translation languages: display label and API value.
const List<(String, String)> _kLanguages = <(String, String)>[
  ('Vietnamese', 'Vietnamese'),
  ('English', 'English'),
  ('Chinese', 'Chinese'),
  ('Japanese', 'Japanese'),
  ('Korean', 'Korean'),
  ('French', 'French'),
  ('German', 'German'),
  ('Spanish', 'Spanish'),
  ('Russian', 'Russian'),
];

enum _SourceMode { document, paste }

class AiTranslateScreen extends ConsumerStatefulWidget {
  const AiTranslateScreen({super.key});

  @override
  ConsumerState<AiTranslateScreen> createState() => _AiTranslateScreenState();
}

class _AiTranslateScreenState extends ConsumerState<AiTranslateScreen> {
  final TextEditingController _text = TextEditingController();

  _SourceMode _mode = _SourceMode.document;
  String? _documentId;
  String? _content;
  bool _extracting = false;
  String? _selection;
  String? _translation;
  bool _translating = false;
  String _sourceValue = ''; // Empty means automatic detection.
  String _targetValue = 'Vietnamese';

  @override
  void dispose() {
    _text.dispose();
    super.dispose();
  }

  Future<void> _showContent() async {
    final String? documentId = _documentId;
    if (documentId == null) return;
    setState(() => _extracting = true);
    try {
      final String text = await ref
          .read(aiRepositoryProvider)
          .extractText(documentId);
      if (mounted) {
        setState(() {
          _content = text;
          _selection = null;
          _translation = null;
        });
      }
    } on Exception catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text(error.toString())));
      }
    } finally {
      if (mounted) setState(() => _extracting = false);
    }
  }

  Future<void> _translate() async {
    final String text = _mode == _SourceMode.document
        ? (_selection ?? '').trim()
        : _text.text.trim();
    if (text.isEmpty) {
      _showHint(
        _mode == _SourceMode.document
            ? 'Highlight text to translate, then press Translate'
            : 'Enter or paste text to translate',
      );
      return;
    }
    setState(() => _translating = true);
    try {
      final String result = await ref
          .read(aiRepositoryProvider)
          .translate(
            text,
            targetLanguage: _targetValue,
            sourceLanguage: _sourceValue.isEmpty ? null : _sourceValue,
          );
      ref.read(lastAiResultsProvider.notifier).setTranslation(text, result);
      if (mounted) setState(() => _translation = result);
    } on Exception catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text(error.toString())));
      }
    } finally {
      if (mounted) setState(() => _translating = false);
    }
  }

  void _showHint(String message) {
    ScaffoldMessenger.of(context)
        .showSnackBar(SnackBar(content: Text(message)));
  }

  void _swapLanguages() {
    if (_sourceValue.isEmpty) return; // Automatic detection cannot be swapped.
    setState(() {
      final String previousSource = _sourceValue;
      _sourceValue = _targetValue;
      _targetValue = previousSource;
    });
  }

  void _copyTranslation() {
    final String? translation = _translation;
    if (translation == null) return;
    Clipboard.setData(ClipboardData(text: translation));
    _showHint('Translation copied');
  }

  @override
  Widget build(BuildContext context) {
    final List<DocumentItem> documents =
        ref.watch(documentsControllerProvider).value?.documents ??
        <DocumentItem>[];
    final bool wide = MediaQuery.of(context).size.width >= 1000;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        Padding(
          padding: const EdgeInsets.fromLTRB(24, 12, 24, 0),
          child: const AiPageHeader(
            title: 'Translate',
            subtitle: 'Select a document and highlight text — or paste text directly.',
            icon: Icons.translate_outlined,
          ),
        ),
        Padding(
          padding: const EdgeInsets.fromLTRB(24, 16, 24, 0),
          child: Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                children: <Widget>[
                  SegmentedButton<_SourceMode>(
                    segments: const <ButtonSegment<_SourceMode>>[
                      ButtonSegment<_SourceMode>(
                        value: _SourceMode.document,
                        icon: Icon(Icons.folder_open_outlined),
                        label: Text('From document'),
                      ),
                      ButtonSegment<_SourceMode>(
                        value: _SourceMode.paste,
                        icon: Icon(Icons.content_paste_go_outlined),
                        label: Text('Paste text'),
                      ),
                    ],
                    selected: <_SourceMode>{_mode},
                    onSelectionChanged: (Set<_SourceMode> selection) =>
                        setState(() {
                          _mode = selection.first;
                          _selection = null;
                          _translation = null;
                        }),
                  ),
                  const SizedBox(height: 16),
                  if (_mode == _SourceMode.document)
                    Row(
                      children: <Widget>[
                        Expanded(
                          child: AiDocumentPicker(
                            documents: documents,
                            value: _documentId,
                            filter: (DocumentItem document) =>
                                document.hasTextContent,
                            labelText: 'Document (PDF, Word, txt/md)',
                            prefixIcon: Icons.description_outlined,
                            emptyHint:
                                'No readable documents (PDF/Word/txt/md)',
                            onChanged: (String? id) => setState(() {
                              _documentId = id;
                              _content = null;
                              _selection = null;
                              _translation = null;
                            }),
                          ),
                        ),
                        const SizedBox(width: 12),
                        FilledButton.tonalIcon(
                          onPressed:
                              _extracting ||
                                  _documentId == null ||
                                  _content != null
                              ? null
                              : _showContent,
                          icon: _extracting
                              ? const SizedBox(
                                  width: 16,
                                  height: 16,
                                  child: CircularProgressIndicator(
                                    strokeWidth: 2,
                                  ),
                                )
                              : const Icon(Icons.visibility_outlined),
                          label: const Text('Show content'),
                        ),
                      ],
                    )
                  else
                    TextField(
                      controller: _text,
                      minLines: 3,
                      maxLines: 6,
                      decoration: const InputDecoration(
                        labelText: 'Text to translate',
                        hintText: 'Paste text here...',
                        alignLabelWithHint: true,
                        border: OutlineInputBorder(),
                      ),
                    ),
                  const SizedBox(height: 16),
                  _languageBar(),
                ],
              ),
            ),
          ),
        ),
        Padding(
          padding: const EdgeInsets.fromLTRB(24, 12, 24, 0),
          child: FilledButton.icon(
            onPressed: _translating ? null : _translate,
            icon: _translating
                ? const SizedBox(
                    width: 16,
                    height: 16,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Icon(Icons.translate),
            label: Text(
              _mode == _SourceMode.document
                  ? 'Translate selection'
                  : 'Translate text',
            ),
          ),
        ),
        Expanded(
          child: Padding(
            padding: const EdgeInsets.fromLTRB(24, 12, 24, 16),
            child: wide
                ? Row(
                    children: <Widget>[
                      Expanded(flex: 3, child: _contentPanel()),
                      const SizedBox(width: 12),
                      Expanded(flex: 2, child: _resultPanel()),
                    ],
                  )
                : Column(
                    children: <Widget>[
                      Expanded(child: _contentPanel()),
                      const SizedBox(height: 12),
                      SizedBox(height: 220, child: _resultPanel()),
                    ],
                  ),
          ),
        ),
      ],
    );
  }

  Widget _languageBar() {
    return Row(
      children: <Widget>[
        Expanded(
          child: DropdownButtonFormField<String>(
            initialValue: _sourceValue,
            decoration: const InputDecoration(
              labelText: 'Source language',
              prefixIcon: Icon(Icons.language_outlined),
            ),
            items: <DropdownMenuItem<String>>[
              const DropdownMenuItem<String>(
                value: '',
                child: Text('Detect automatically'),
              ),
              for (final (String label, String value) in _kLanguages)
                DropdownMenuItem<String>(value: value, child: Text(label)),
            ],
            onChanged: (String? value) =>
                setState(() => _sourceValue = value ?? ''),
          ),
        ),
        IconButton(
          tooltip: 'Swap languages',
          onPressed: _sourceValue.isEmpty ? null : _swapLanguages,
          icon: const Icon(Icons.swap_horiz),
        ),
        Expanded(
          child: DropdownButtonFormField<String>(
            initialValue: _targetValue,
            decoration: const InputDecoration(
              labelText: 'Target language',
              prefixIcon: Icon(Icons.flag_outlined),
            ),
            items: <DropdownMenuItem<String>>[
              for (final (String label, String value) in _kLanguages)
                DropdownMenuItem<String>(value: value, child: Text(label)),
            ],
            onChanged: (String? value) =>
                setState(() => _targetValue = value ?? _targetValue),
          ),
        ),
      ],
    );
  }

  Widget _contentPanel() {
    if (_mode == _SourceMode.paste) {
      return Card(
        child: Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              Icon(
                Icons.content_paste_go_outlined,
                size: 40,
                color: Theme.of(context).hintColor,
              ),
              const SizedBox(height: 8),
              Text(
                'Your pasted text is shown above — click "Translate text" to continue.',
                textAlign: TextAlign.center,
                style: TextStyle(color: Theme.of(context).hintColor),
              ),
            ],
          ),
        ),
      );
    }
    if (_extracting) {
      return const Card(child: Center(child: CircularProgressIndicator()));
    }
    final String? content = _content;
    if (content == null) {
      return Card(
        child: Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              Icon(
                Icons.document_scanner_outlined,
                size: 40,
                color: Theme.of(context).hintColor,
              ),
              const SizedBox(height: 8),
              Text(
                'Select a document and press "Show content",\nthen highlight text to translate.',
                textAlign: TextAlign.center,
                style: TextStyle(color: Theme.of(context).hintColor),
              ),
            ],
          ),
        ),
      );
    }
    return Card(
      clipBehavior: Clip.antiAlias,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 8),
            child: Row(
              children: <Widget>[
                Expanded(
                  child: Text(
                    'Document content',
                    style: Theme.of(context).textTheme.titleSmall,
                  ),
                ),
                if (_selection != null && _selection!.trim().isNotEmpty)
                  Flexible(
                    child: Text(
                      '${_selection!.trim().length} characters selected',
                      style: TextStyle(
                        color: Theme.of(context).colorScheme.primary,
                        fontSize: 12,
                      ),
                    ),
                  ),
              ],
            ),
          ),
          const Divider(height: 1),
          Expanded(
            child: SelectionArea(
              onSelectionChanged: (SelectedContent? selected) {
                if (!mounted) return;
                final String? plain = selected?.plainText.trim();
                // Giữ lại vùng chọn gần nhất: bấm nút Dịch làm mất focus
                // vùng chọn (sự kiện null chạy TRƯỚC onPressed của nút),
                // nên không bao giờ clear về null ở đây — chỉ xoá khi đổi
                // tài liệu / đổi chế độ / tải lại nội dung.
                if (plain != null && plain.isNotEmpty) {
                  setState(() => _selection = plain);
                }
              },
              child: Scrollbar(
                child: SingleChildScrollView(
                  padding: const EdgeInsets.fromLTRB(16, 12, 16, 16),
                  child: Text(
                    content,
                    style: const TextStyle(fontSize: 14, height: 1.6),
                  ),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _resultPanel() {
    final String? translation = _translation;
    return Card(
      clipBehavior: Clip.antiAlias,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 12, 8, 8),
            child: Row(
              children: <Widget>[
                Expanded(
                  child: Text(
                    'Translation',
                    style: Theme.of(context).textTheme.titleSmall,
                  ),
                ),
                if (translation != null)
                  IconButton(
                    tooltip: 'Copy',
                    onPressed: _copyTranslation,
                    icon: const Icon(Icons.copy_outlined, size: 18),
                  ),
              ],
            ),
          ),
          const Divider(height: 1),
          Expanded(
            child: translation == null
                ? Center(
                    child: Text(
                      'Your translation will appear here',
                      style: TextStyle(color: Theme.of(context).hintColor),
                    ),
                  )
                : Scrollbar(
                    child: SingleChildScrollView(
                      padding: const EdgeInsets.all(16),
                      child: Text(
                        translation,
                        style: const TextStyle(fontSize: 14, height: 1.6),
                      ),
                    ),
                  ),
          ),
        ],
      ),
    );
  }
}
