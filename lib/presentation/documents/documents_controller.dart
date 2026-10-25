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

class DocumentsState {
  const DocumentsState({
    this.folders = const <DocumentFolder>[],
    this.documents = const <DocumentItem>[],
    this.selectedFolderId,
    this.selectionMode = false,
    this.selection = const <String>{},
  });

  final List<DocumentFolder> folders;
  final List<DocumentItem> documents;
  final String? selectedFolderId;
  final bool selectionMode;
  final Set<String> selection;

  DocumentsState copyWith({
    List<DocumentFolder>? folders,
    List<DocumentItem>? documents,
    String? selectedFolderId,
    bool? selectionMode,
    Set<String>? selection,
  }) {
    return DocumentsState(
      folders: folders ?? this.folders,
      documents: documents ?? this.documents,
      selectedFolderId: selectedFolderId ?? this.selectedFolderId,
      selectionMode: selectionMode ?? this.selectionMode,
      selection: selection ?? this.selection,
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

  Future<void> _reload() async {
    final DocumentsState current = state.value ?? const DocumentsState();
    final List<DocumentItem> docs = await _repo.listDocuments(
      folderId: current.selectedFolderId,
    );
    state = AsyncData(current.copyWith(documents: docs));
  }

  Future<void> selectFolder(String? folderId) async {
    final DocumentsState current = state.value ?? const DocumentsState();
    final List<DocumentItem> docs = await _repo.listDocuments(
      folderId: folderId,
    );
    state = AsyncData(
      current.copyWith(selectedFolderId: folderId, documents: docs),
    );
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
    final List<DocumentItem> docs = await _repo.listDocuments(
      folderId: wasSelected ? null : current.selectedFolderId,
    );
    state = AsyncData(
      current.copyWith(
        folders: folders,
        documents: docs,
        selectedFolderId: wasSelected ? null : current.selectedFolderId,
      ),
    );
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
