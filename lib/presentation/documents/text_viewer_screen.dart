/// Xem tài liệu dạng văn bản (txt/md/Word/PDF-scan-đã-trích) với bôi đen
/// + dịch vùng chọn — dùng chung UX với [PdfViewerScreen].
library;

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart' show SelectedContent;

class TextViewerScreen extends StatefulWidget {
  const TextViewerScreen({
    super.key,
    required this.fileName,
    required this.text,
    this.onTranslateSelection,
  });

  final String fileName;
  final String text;
  final Future<String> Function(String text)? onTranslateSelection;

  @override
  State<TextViewerScreen> createState() => _TextViewerScreenState();
}

class _TextViewerScreenState extends State<TextViewerScreen> {
  String? _selectedText;
  String? _translation;
  bool _translating = false;

  Future<void> _translateSelection() async {
    final String? selectedText = _selectedText;
    final Future<String> Function(String text)? translate =
        widget.onTranslateSelection;
    if (selectedText == null ||
        selectedText.trim().isEmpty ||
        translate == null) {
      return;
    }
    setState(() => _translating = true);
    try {
      final String result = await translate(selectedText);
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

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text(
          widget.fileName,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
        ),
      ),
      body: SelectionArea(
        onSelectionChanged: (SelectedContent? content) {
          if (!mounted) return;
          final String? selection = content?.plainText.trim();
          setState(() {
            _selectedText = (selection == null || selection.isEmpty)
                ? null
                : selection;
            if (_selectedText == null) _translation = null;
          });
        },
        child: Scrollbar(
          child: SingleChildScrollView(
            padding: const EdgeInsets.fromLTRB(24, 16, 24, 96),
            child: Text(
              widget.text,
              style: const TextStyle(fontSize: 15, height: 1.6),
            ),
          ),
        ),
      ),
      bottomSheet: _selectedText == null || widget.onTranslateSelection == null
          ? null
          : Material(
              elevation: 8,
              child: SafeArea(
                child: Padding(
                  padding: const EdgeInsets.fromLTRB(16, 8, 16, 8),
                  child: Row(
                    children: <Widget>[
                      Expanded(
                        child: Text(
                          _translation == null
                              ? 'Đã chọn: ${_selectedText!}'
                              : 'Bản dịch: $_translation',
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                      const SizedBox(width: 8),
                      FilledButton.icon(
                        onPressed: _translating ? null : _translateSelection,
                        icon: _translating
                            ? const SizedBox(
                                width: 16,
                                height: 16,
                                child: CircularProgressIndicator(
                                  strokeWidth: 2,
                                ),
                              )
                            : const Icon(Icons.translate),
                        label: const Text('Dịch vùng chọn'),
                      ),
                    ],
                  ),
                ),
              ),
            ),
    );
  }
}
