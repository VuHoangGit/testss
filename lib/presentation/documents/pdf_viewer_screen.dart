import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:syncfusion_flutter_pdfviewer/pdfviewer.dart';

class PdfViewerScreen extends StatefulWidget {
  const PdfViewerScreen({
    super.key,
    required this.fileName,
    required this.bytes,
    this.onTranslateSelection,
  });

  final String fileName;
  final Uint8List bytes;
  final Future<String> Function(String text)? onTranslateSelection;

  @override
  State<PdfViewerScreen> createState() => _PdfViewerScreenState();
}

class _PdfViewerScreenState extends State<PdfViewerScreen> {
  final PdfViewerController _controller = PdfViewerController();
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
        actions: <Widget>[
          IconButton(
            tooltip: 'Trang trước',
            onPressed: () => _controller.previousPage(),
            icon: const Icon(Icons.chevron_left),
          ),
          IconButton(
            tooltip: 'Trang sau',
            onPressed: () => _controller.nextPage(),
            icon: const Icon(Icons.chevron_right),
          ),
        ],
      ),
      body: SfPdfViewer.memory(
        widget.bytes,
        controller: _controller,
        onTextSelectionChanged: (PdfTextSelectionChangedDetails details) {
          if (!mounted) return;
          setState(() {
            _selectedText = details.selectedText?.trim();
            if (_selectedText == null) _translation = null;
          });
        },
        canShowScrollHead: true,
        canShowScrollStatus: true,
        enableDoubleTapZooming: true,
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
