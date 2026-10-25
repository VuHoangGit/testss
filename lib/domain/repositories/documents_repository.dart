/// Hợp đồng tầng domain cho kho tài liệu (Sprint 2).
library;

import 'dart:typed_data';

import '../entities/document_entities.dart';

abstract interface class DocumentsRepository {
  Future<List<DocumentFolder>> listFolders();

  Future<DocumentFolder> createFolder(String name);

  Future<void> deleteFolder(String folderId);

  /// [folderId] null = lấy toàn bộ tài liệu của user.
  Future<List<DocumentItem>> listDocuments({String? folderId});

  /// Upload nội dung file (bytes — chạy được cả web lẫn native).
  Future<DocumentItem> uploadDocument({
    required String fileName,
    required Uint8List bytes,
    String? folderId,
    void Function(int sent, int total)? onProgress,
  });

  /// Tải nội dung gốc về bộ nhớ (UI/platform tự lưu ra đĩa qua FileSaver).
  Future<Uint8List> downloadDocument(String documentId);

  Future<void> deleteDocument(String documentId);

  /// Gộp nhiều PDF (theo thứ tự) thành tài liệu mới.
  Future<DocumentItem> mergeDocuments({
    required List<String> documentIds,
    required String name,
  });

  /// Tách trang theo phạm vi "1-3,5" → danh sách tài liệu PDF mới.
  Future<List<DocumentItem>> splitDocument(
    String documentId, {
    required String ranges,
  });

  Future<DocumentItem> protectDocument(
    String documentId, {
    required String password,
  });

  Future<DocumentItem> unprotectDocument(
    String documentId, {
    required String password,
  });
}
