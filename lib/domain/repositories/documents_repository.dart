/// Hợp đồng tầng domain cho kho tài liệu (Sprint 2).
library;

import 'dart:typed_data';

import '../entities/document_entities.dart';

/// Kiểu sắp xếp danh sách tài liệu (backend `?sort=`).
enum DocumentsSort {
  /// Mới tải lên trước (mặc định).
  created,

  /// Mở gần nhất trước, file chưa từng mở xếp cuối (TOOLS → Recent).
  recent,
}

abstract interface class DocumentsRepository {
  Future<List<DocumentFolder>> listFolders();

  Future<DocumentFolder> createFolder(String name);

  Future<void> deleteFolder(String folderId);

  /// [folderId] null = lấy toàn bộ tài liệu của user.
  ///
  /// [search] tìm gần đúng theo tên file; [favoritesOnly] chỉ file đã gắn sao;
  /// [sort] chọn thứ tự (mặc định theo lần tải lên).
  Future<List<DocumentItem>> listDocuments({
    String? folderId,
    String? search,
    bool favoritesOnly,
    DocumentsSort sort,
  });

  /// Gắn/gỡ sao tài liệu. Trả về bản cập nhật từ server.
  Future<DocumentItem> setFavorite(String documentId, {required bool favorite});

  /// Đánh dấu vừa mở tài liệu (cập nhật `last_opened_at` cho Recent).
  Future<DocumentItem> markOpened(String documentId);

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

  // -- Lịch sử phiên bản -------------------------------------------------

  /// Danh sách bản cũ của tài liệu (mới nhất trước).
  Future<List<DocumentVersionItem>> listVersions(String documentId);

  /// Upload bản mới: bản hiện tại được giữ lại thành phiên bản 1.
  Future<DocumentItem> uploadNewVersion({
    required String documentId,
    required String fileName,
    required Uint8List bytes,
    String label = '',
    void Function(int sent, int total)? onProgress,
  });

  /// Khôi phục một bản cũ thành bản hiện tại (bản hiện tại không mất).
  Future<DocumentItem> restoreVersion({
    required String documentId,
    required String versionId,
  });

  /// Xóa một bản cũ khỏi lịch sử (file + row).
  Future<void> deleteVersion({
    required String documentId,
    required String versionId,
  });

  /// So sánh 2 bản: [newVersionId] null = so với bản hiện tại.
  ///
  /// Tốn 1 lượt AI (trừ credit) trừ khi 2 bản giống hệt nhau.
  Future<VersionDiffResult> diffVersions({
    required String documentId,
    required String oldVersionId,
    String? newVersionId,
  });
}
