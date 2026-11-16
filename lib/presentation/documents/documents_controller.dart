/// Điều khiển tab Tài liệu: thư mục, upload, tải xuống, công cụ PDF.
///
/// Mỗi thao tác gọi repository rồi reload danh sách; lỗi nghiệp vụ ném lên
/// UI (SnackBar) — controller không giữ message riêng.
library;

import 'dart:typed_data';

import 'package:file_picker/file_picker.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/files/file_saver.dart';
import '../../domain/entities/document_entities.dart';
import '../../domain/repositories/documents_repository.dart';
import 'documents_providers.dart';

/// Bộ lọc khung nhìn đang chọn ở tab Files (TOOLS → Recent/Favorites).
enum DocumentsViewFilter {
  /// Toàn bộ file trong thư mục đang chọn (mặc định).
  all,

  /// Chỉ file đã gắn sao.
  favorites,

  /// Xếp theo lần mở gần nhất.
  recent,
}

class DocumentsState {
  const DocumentsState({
    this.folders = const <DocumentFolder>[],
    this.documents = const <DocumentItem>[],
    this.selectedFolderId,
    this.selectionMode = false,
    this.selection = const <String>{},
    this.viewFilter = DocumentsViewFilter.all,
  });

  final List<DocumentFolder> folders;
  final List<DocumentItem> documents;
  final String? selectedFolderId;
  final bool selectionMode;
  final Set<String> selection;
  final DocumentsViewFilter viewFilter;

  DocumentsState copyWith({
    List<DocumentFolder>? folders,
    List<DocumentItem>? documents,
    String? selectedFolderId,
    bool? selectionMode,
    Set<String>? selection,
    DocumentsViewFilter? viewFilter,
  }) {
    return DocumentsState(
      folders: folders ?? this.folders,
      documents: documents ?? this.documents,
      selectedFolderId: selectedFolderId ?? this.selectedFolderId,
      selectionMode: selectionMode ?? this.selectionMode,
      selection: selection ?? this.selection,
      viewFilter: viewFilter ?? this.viewFilter,
    );
  }
}

class DocumentsController extends AsyncNotifier<DocumentsState> {
  DocumentsRepository get _repo => ref.read(documentsRepositoryProvider);

  @override
  Future<DocumentsState> build() async {
    final List<DocumentFolder> folders = await _repo.listFolders();
    final List<DocumentItem> docs = await _repo.listDocuments();
    return DocumentsState(folders: folders, documents: docs);
  }

  /// Danh sách theo trạng thái hiện tại (folder + bộ lọc Recent/Favorites).
  Future<List<DocumentItem>> _fetch(DocumentsState current) =>
      _repo.listDocuments(
        // Favorites/Recent là khung nhìn toàn kho, không ghép folder
        folderId: current.viewFilter == DocumentsViewFilter.all
            ? current.selectedFolderId
            : null,
        favoritesOnly: current.viewFilter == DocumentsViewFilter.favorites,
        sort: current.viewFilter == DocumentsViewFilter.recent
            ? DocumentsSort.recent
            : DocumentsSort.created,
      );

  Future<void> _reload() async {
    final DocumentsState current = state.value ?? const DocumentsState();
    final List<DocumentItem> docs = await _fetch(current);
    state = AsyncData(current.copyWith(documents: docs));
  }

  Future<void> selectFolder(String? folderId) async {
    final DocumentsState current = state.value ?? const DocumentsState();
    // Chọn folder = rời khung nhìn Recent/Favorites về All
    final DocumentsState next = current.copyWith(
      selectedFolderId: folderId,
      viewFilter: DocumentsViewFilter.all,
    );
    final List<DocumentItem> docs = await _fetch(next);
    state = AsyncData(next.copyWith(documents: docs));
  }

  /// Mở khung nhìn TOOLS (Recent/Favorites) — tải lại danh sách tương ứng.
  Future<void> setViewFilter(DocumentsViewFilter filter) async {
    if (filter == (state.value?.viewFilter ?? DocumentsViewFilter.all)) {
      return;
    }
    final DocumentsState current = state.value ?? const DocumentsState();
    final DocumentsState next = current.copyWith(viewFilter: filter);
    final List<DocumentItem> docs = await _fetch(next);
    state = AsyncData(next.copyWith(documents: docs));
  }

  /// Gắn/gỡ sao: optimistic UI, rollback nếu server lỗi. Đang xem
  /// Favorites mà gỡ sao thì bỏ file khỏi danh sách.
  Future<void> toggleFavorite(String documentId) async {
    final DocumentsState current = state.value ?? const DocumentsState();
    final int index = current.documents.indexWhere(
      (DocumentItem d) => d.id == documentId,
    );
    if (index < 0) return;
    final DocumentItem old = current.documents[index];
    final DocumentItem optimistic = old.copyWith(isFavorite: !old.isFavorite);
    final List<DocumentItem> updated = List<DocumentItem>.of(current.documents);
    updated[index] = optimistic;
    state = AsyncData(current.copyWith(documents: updated));
    try {
      await _repo.setFavorite(documentId, favorite: !old.isFavorite);
    } on Exception {
      state = AsyncData(current.copyWith(documents: current.documents));
      rethrow;
    }
    if (optimistic.isFavorite == false &&
        current.viewFilter == DocumentsViewFilter.favorites) {
      // Gỡ sao trong khung nhìn Favorites → file rời khỏi danh sách
      await _reload();
    }
  }

  /// Đánh dấu vừa mở file (feed Recent). Cập nhật item trong state để
  /// dashboard đổi thứ tự ngay mà không cần reload.
  Future<void> markOpened(String documentId) async {
    final DocumentsState current = state.value ?? const DocumentsState();
    final int index = current.documents.indexWhere(
      (DocumentItem d) => d.id == documentId,
    );
    if (index < 0) return;
    try {
      final DocumentItem fresh = await _repo.markOpened(documentId);
      final List<DocumentItem> updated = List<DocumentItem>.of(
        current.documents,
      );
      updated[index] = fresh;
      state = AsyncData((state.value ?? current).copyWith(documents: updated));
    } on Exception {
      // Chỉ là metadata Recent — mở file không nên văng lỗi vì đánh dấu
    }
  }

  Future<void> createFolder(String name) async {
    await _repo.createFolder(name);
    final List<DocumentFolder> folders = await _repo.listFolders();
    final DocumentsState current = state.value ?? const DocumentsState();
    state = AsyncData(current.copyWith(folders: folders));
  }

  Future<void> deleteFolder(String folderId) async {
    await _repo.deleteFolder(folderId);
    final DocumentsState current = state.value ?? const DocumentsState();
    final List<DocumentFolder> folders = await _repo.listFolders();
    final bool wasSelected = current.selectedFolderId == folderId;
    final DocumentsState next = current.copyWith(
      selectedFolderId: wasSelected ? null : current.selectedFolderId,
    );
    final List<DocumentItem> docs = await _fetch(next);
    state = AsyncData(next.copyWith(folders: folders, documents: docs));
  }

  /// Mở file picker, đọc bytes và upload. Trả về tên file đã tải lên
  /// (null nếu người dùng hủy picker).
  Future<String?> pickAndUpload({
    String? folderId,
    void Function(int sent, int total)? onProgress,
  }) async {
    // file_picker 13: API static; trả về danh sách rỗng nếu người dùng hủy
    final List<PlatformFile> picked = await FilePicker.pickFiles(
      type: FileType.custom,
      allowedExtensions: <String>[
        'pdf',
        'doc',
        'docx',
        'xls',
        'xlsx',
        'ppt',
        'pptx',
        'png',
        'jpg',
        'jpeg',
        'gif',
        'txt',
        'md',
        'zip',
      ],
    );
    if (picked.isEmpty) {
      return null; // người dùng hủy
    }
    final PlatformFile file = picked.first;
    final Uint8List bytes = await file.readAsBytes();
    await _repo.uploadDocument(
      fileName: file.name,
      bytes: bytes,
      folderId: folderId,
      onProgress: onProgress,
    );
    await _reload();
    return file.name;
  }

  /// Upload một ảnh vừa chụp/chọn thành tài liệu mới, trả về tài liệu server
  /// vừa tạo để màn hình OCR chọn đúng nó ngay (ảnh cũng hiện trong tab Files).
  ///
  /// Ảnh vào thư mục đang mở (`selectedFolderId`, null = kho chung) — giống
  /// thao tác upload thường.
  Future<DocumentItem> uploadPhoto({
    required String fileName,
    required Uint8List bytes,
    void Function(int sent, int total)? onProgress,
  }) async {
    final DocumentItem document = await _repo.uploadDocument(
      fileName: fileName,
      bytes: bytes,
      folderId: state.value?.selectedFolderId,
      onProgress: onProgress,
    );
    await _reload();
    return document;
  }

  /// Tải document và lưu qua FileSaver. Trả về tên/đường dẫn đã lưu,
  /// null nếu người dùng hủy.
  Future<String?> downloadDocument(DocumentItem doc) async {
    final Uint8List bytes = await _repo.downloadDocument(doc.id);
    return const FileSaver().saveBytes(
      fileName: doc.name,
      bytes: bytes,
      mimeType: doc.mimeType,
    );
  }

  Future<void> deleteDocument(String documentId) async {
    await _repo.deleteDocument(documentId);
    await _reload();
  }

  void toggleSelect(String documentId) {
    final DocumentsState current = state.value ?? const DocumentsState();
    final Set<String> next = Set<String>.of(current.selection);
    if (!next.add(documentId)) {
      next.remove(documentId);
    }
    state = AsyncData(
      current.copyWith(
        selection: next,
        selectionMode: next.isNotEmpty || current.selectionMode,
      ),
    );
  }

  void enterSelectionMode() {
    final DocumentsState current = state.value ?? const DocumentsState();
    state = AsyncData(current.copyWith(selectionMode: true));
  }

  /// Đặt lại danh sách đang chọn (voice merge dùng) + bật selection mode.
  void setSelection(Iterable<String> documentIds) {
    final DocumentsState current = state.value ?? const DocumentsState();
    final Set<String> next = documentIds.toSet();
    state = AsyncData(
      current.copyWith(
        selection: next,
        selectionMode: next.isNotEmpty || current.selectionMode,
      ),
    );
  }

  void cancelSelection() {
    final DocumentsState current = state.value ?? const DocumentsState();
    state = AsyncData(
      current.copyWith(selectionMode: false, selection: const <String>{}),
    );
  }

  /// Gộp các tài liệu đang chọn. Trả về tên tài liệu mới.
  Future<String> mergeSelected(String name) async {
    final DocumentsState current = state.value ?? const DocumentsState();
    final DocumentItem merged = await _repo.mergeDocuments(
      documentIds: current.selection.toList(growable: false),
      name: name,
    );
    cancelSelection();
    await _reload();
    return merged.name;
  }

  Future<List<String>> splitDocument(
    String documentId, {
    required String ranges,
  }) async {
    final List<DocumentItem> parts = await _repo.splitDocument(
      documentId,
      ranges: ranges,
    );
    await _reload();
    return parts.map((DocumentItem d) => d.name).toList(growable: false);
  }

  Future<String> protectDocument(
    String documentId, {
    required String password,
  }) async {
    final DocumentItem doc = await _repo.protectDocument(
      documentId,
      password: password,
    );
    await _reload();
    return doc.name;
  }

  Future<String> unprotectDocument(
    String documentId, {
    required String password,
  }) async {
    final DocumentItem doc = await _repo.unprotectDocument(
      documentId,
      password: password,
    );
    await _reload();
    return doc.name;
  }
}
