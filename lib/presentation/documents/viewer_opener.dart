/// Mở PDF viewer qua root navigator — dùng được từ DocumentsScreen lẫn
/// voice executor (không cần BuildContext của screen đang hiển thị).
library;

import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/navigation/root_navigator_key.dart';
import '../../domain/entities/document_entities.dart';
import '../../domain/repositories/ai_repository.dart';
import '../../domain/repositories/documents_repository.dart';
import '../ai/ai_providers.dart';
import 'documents_providers.dart';
import 'pdf_viewer_screen.dart';

/// Tải bytes rồi đẩy [PdfViewerScreen]. Trả về câu phản hồi cho người gọi
/// (voice dùng để đọc lại bằng TTS); ném Exception như các thao tác khác.
Future<String> openPdfViewer(WidgetRef ref, DocumentItem doc) async {
  final DocumentsRepository repository = ref.read(documentsRepositoryProvider);
  final AiRepository ai = ref.read(aiRepositoryProvider);
  final Uint8List bytes = await repository.downloadDocument(doc.id);
  final BuildContext? context = rootNavigatorKey.currentContext;
  if (context == null || !context.mounted) {
    return 'Không mở được trình xem tài liệu';
  }
  await Navigator.of(context).push<void>(
    MaterialPageRoute<void>(
      builder: (_) => PdfViewerScreen(
        fileName: doc.name,
        bytes: bytes,
        onTranslateSelection: (String text) => ai.translate(text),
      ),
    ),
  );
  return 'Đã mở "${doc.name}"';
}
