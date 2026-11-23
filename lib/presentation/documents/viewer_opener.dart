/// Mở trình xem tài liệu qua root navigator — dùng được từ DocumentsScreen
/// lẫn voice executor (không cần BuildContext của screen đang hiển thị).
library;

import 'dart:typed_data';

import 'package:flutter/material.dart';

import '../../core/files/pdf_browser_opener.dart';
import '../../core/navigation/root_navigator_key.dart';
import '../../domain/entities/document_entities.dart';
import '../../domain/repositories/ai_repository.dart';
import '../../domain/repositories/documents_repository.dart';
import 'image_viewer_screen.dart';
import 'pdf_viewer_screen.dart';
import 'text_viewer_screen.dart';

/// Tải bytes rồi đẩy [PdfViewerScreen]. Trả về câu phản hồi cho người gọi
/// (voice dùng để đọc lại bằng TTS); ném Exception như các thao tác khác.
Future<String> openPdfViewer({
  required DocumentsRepository repository,
  required AiRepository aiRepository,
  required DocumentItem doc,
}) async {
  final bool openedInBrowser = await openPdfInBrowser(
    fileName: doc.name,
    download: () => repository.downloadDocument(doc.id),
  );
  if (openedInBrowser) {
    return 'Opened "${doc.name}" in browser';
  }
  final Uint8List bytes = await repository.downloadDocument(doc.id);
  final BuildContext? context = rootNavigatorKey.currentContext;
  if (context == null || !context.mounted) {
    return 'Could not open the document viewer';
  }
  await Navigator.of(context).push<void>(
    MaterialPageRoute<void>(
      builder: (_) => PdfViewerScreen(
        fileName: doc.name,
        bytes: bytes,
        subtitle: _describeDoc(doc),
        onTranslateSelection: (String text) => aiRepository.translate(text),
      ),
    ),
  );
  return 'Opened "${doc.name}"';
}

/// Trích văn bản rồi đẩy [TextViewerScreen] (PDF viewer đã lo file PDF).
Future<String> _openTextViewer({
  required AiRepository aiRepository,
  required DocumentItem doc,
}) async {
  final String text = await aiRepository.extractText(doc.id);
  final BuildContext? context = rootNavigatorKey.currentContext;
  if (context == null || !context.mounted) {
    return 'Could not open the document viewer';
  }
  await Navigator.of(context).push<void>(
    MaterialPageRoute<void>(
      builder: (_) => TextViewerScreen(
        fileName: doc.name,
        text: text,
        onTranslateSelection: (String selection) =>
            aiRepository.translate(selection),
      ),
    ),
  );
  return 'Opened "${doc.name}"';
}

/// Tải bytes rồi đẩy [ImageViewerScreen].
Future<String> _openImageViewer({
  required DocumentsRepository repository,
  required DocumentItem doc,
}) async {
  final Uint8List bytes = await repository.downloadDocument(doc.id);
  final BuildContext? context = rootNavigatorKey.currentContext;
  if (context == null || !context.mounted) {
    return 'Could not open the document viewer';
  }
  await Navigator.of(context).push<void>(
    MaterialPageRoute<void>(
      builder: (_) => ImageViewerScreen(fileName: doc.name, bytes: bytes),
    ),
  );
  return 'Opened "${doc.name}"';
}

/// Metadata một dòng cho toolbar của viewer (kích thước + số trang nếu có).
String _describeDoc(DocumentItem doc) {
  final double mb = doc.sizeBytes / (1024 * 1024);
  final String size = mb >= 1
      ? '${mb.toStringAsFixed(1)} MB'
      : '${(doc.sizeBytes / 1024).toStringAsFixed(0)} KB';
  return doc.pageCount != null ? '${doc.pageCount} pages · $size' : size;
}

/// Điều hướng theo loại file: PDF → viewer gốc, Word/txt/md → trình xem văn
/// bản (bôi đen dịch được), ảnh → trình xem ảnh. Loại khác → gợi ý tải về.
Future<String> openDocumentViewer({
  required DocumentsRepository repository,
  required AiRepository aiRepository,
  required DocumentItem doc,
}) async {
  if (doc.isPdf) {
    return openPdfViewer(
      repository: repository,
      aiRepository: aiRepository,
      doc: doc,
    );
  }
  if (doc.hasTextContent) {
    return _openTextViewer(aiRepository: aiRepository, doc: doc);
  }
  if (doc.isImage) {
    return _openImageViewer(repository: repository, doc: doc);
  }
  return '"${doc.name}" cannot be previewed — download it and open it with a suitable app.';
}
