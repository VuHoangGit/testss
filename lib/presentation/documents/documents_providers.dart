/// Provider cho kho tài liệu (Sprint 2) — tách file khỏi providers.dart cho gọn.
library;

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../data/repositories/documents_repository_impl.dart';
import '../../domain/repositories/documents_repository.dart';
import '../providers.dart';
import 'documents_controller.dart';

final Provider<DocumentsRepository> documentsRepositoryProvider =
    Provider<DocumentsRepository>(
  (Ref ref) => DocumentsRepositoryImpl(dio: ref.watch(apiDioProvider)),
);

final AsyncNotifierProvider<DocumentsController, DocumentsState>
    documentsControllerProvider =
    AsyncNotifierProvider<DocumentsController, DocumentsState>(
  DocumentsController.new,
);
