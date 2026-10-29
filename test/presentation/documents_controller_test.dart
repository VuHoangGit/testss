/// Test DocumentsController: bộ lọc Recent/Favorites + toggle sao optimistic.
library;

import 'dart:typed_data';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:testss/domain/entities/document_entities.dart';
import 'package:testss/domain/repositories/documents_repository.dart';
import 'package:testss/presentation/documents/documents_controller.dart';
import 'package:testss/presentation/documents/documents_providers.dart';

class _FakeRepo implements DocumentsRepository {
  _FakeRepo(this.docs);

  final List<DocumentItem> docs;
  DocumentsSort? lastSort;
  bool? lastFavoritesOnly;
  String? lastFolderId;
  Object? favoriteError;

  @override
  Future<List<DocumentItem>> listDocuments({
    String? folderId,
    String? search,
    bool favoritesOnly = false,
    DocumentsSort sort = DocumentsSort.created,
  }) async {
    lastFolderId = folderId;
    lastFavoritesOnly = favoritesOnly;
    lastSort = sort;
    return docs;
  }

  @override
  Future<DocumentItem> setFavorite(
    String documentId, {
    required bool favorite,
  }) async {
    if (favoriteError != null) {
      throw favoriteError! as Exception;
    }
    final DocumentItem doc = docs.firstWhere(
      (DocumentItem d) => d.id == documentId,
    );
    return doc.copyWith(isFavorite: favorite);
  }

  @override
  Future<DocumentItem> markOpened(String documentId) async {
    final DocumentItem doc = docs.firstWhere(
      (DocumentItem d) => d.id == documentId,
    );
    return doc.copyWith(
      lastOpenedAt: DateTime.fromMillisecondsSinceEpoch(1_000),
    );
  }

  @override
  Future<DocumentItem> mergeDocuments({
    required List<String> documentIds,
    required String name,
  }) => throw UnimplementedError();

  @override
  Future<DocumentFolder> createFolder(String name) =>
      throw UnimplementedError();

  @override
  Future<void> deleteDocument(String documentId) => throw UnimplementedError();

  @override
  Future<void> deleteFolder(String folderId) => throw UnimplementedError();

  @override
  Future<Uint8List> downloadDocument(String documentId) =>
      throw UnimplementedError();

  @override
  Future<List<DocumentFolder>> listFolders() async => const <DocumentFolder>[];

  @override
  Future<DocumentItem> protectDocument(
    String documentId, {
    required String password,
  }) => throw UnimplementedError();

  @override
  Future<DocumentItem> unprotectDocument(
    String documentId, {
    required String password,
  }) => throw UnimplementedError();

  @override
  Future<DocumentItem> uploadDocument({
    required String fileName,
    required Uint8List bytes,
    String? folderId,
    void Function(int sent, int total)? onProgress,
  }) => throw UnimplementedError();

  @override
  Future<List<DocumentItem>> splitDocument(
    String documentId, {
    required String ranges,
  }) => throw UnimplementedError();
}

DocumentItem _doc(String id, {bool favorite = false}) => DocumentItem(
  id: id,
  name: '$id.pdf',
  mimeType: 'application/pdf',
  sizeBytes: 100,
  createdAt: DateTime.fromMillisecondsSinceEpoch(0),
  isFavorite: favorite,
);

Future<(ProviderContainer, _FakeRepo)> _boot({
  List<DocumentItem> docs = const <DocumentItem>[],
}) async {
  final _FakeRepo repo = _FakeRepo(docs);
  final ProviderContainer container = ProviderContainer(
    overrides: [documentsRepositoryProvider.overrideWithValue(repo)],
  );
  addTearDown(container.dispose);
  await container.read(documentsControllerProvider.future);
  return (container, repo);
}

void main() {
  test('setViewFilter(favorites) tải toàn kho với favorites_only', () async {
    final (ProviderContainer container, _FakeRepo repo) = await _boot(
      docs: <DocumentItem>[_doc('a'), _doc('b')],
    );
    await container
        .read(documentsControllerProvider.notifier)
        .setViewFilter(DocumentsViewFilter.favorites);
    final DocumentsState state =
        container.read(documentsControllerProvider).value!;
    expect(state.viewFilter, DocumentsViewFilter.favorites);
    expect(repo.lastFavoritesOnly, isTrue);
    expect(repo.lastFolderId, isNull); // không ghép folder đang chọn
  });

  test('setViewFilter(recent) → sort=recent; chọn folder quay về all', () async {
    final (ProviderContainer container, _FakeRepo repo) = await _boot(
      docs: <DocumentItem>[_doc('a')],
    );
    await container
        .read(documentsControllerProvider.notifier)
        .setViewFilter(DocumentsViewFilter.recent);
    expect(repo.lastSort, DocumentsSort.recent);

    await container
        .read(documentsControllerProvider.notifier)
        .selectFolder('f1');
    final DocumentsState state =
        container.read(documentsControllerProvider).value!;
    expect(state.viewFilter, DocumentsViewFilter.all);
    expect(state.selectedFolderId, 'f1');
  });

  test('toggleFavorite lật optimistic và giữ sau khi server OK', () async {
    final (ProviderContainer container, _) = await _boot(
      docs: <DocumentItem>[_doc('a')],
    );
    final DocumentsController controller = container.read(
      documentsControllerProvider.notifier,
    );
    await controller.toggleFavorite('a');
    expect(
      container.read(documentsControllerProvider).value!.documents.first
          .isFavorite,
      isTrue,
    );
    await controller.toggleFavorite('a');
    expect(
      container.read(documentsControllerProvider).value!.documents.first
          .isFavorite,
      isFalse,
    );
  });

  test('toggleFavorite rollback khi server lỗi', () async {
    final (ProviderContainer container, _FakeRepo repo) = await _boot(
      docs: <DocumentItem>[_doc('a')],
    );
    repo.favoriteError = Exception('Lỗi mạng');
    final DocumentsController controller = container.read(
      documentsControllerProvider.notifier,
    );
    await expectLater(controller.toggleFavorite('a'), throwsException);
    expect(
      container.read(documentsControllerProvider).value!.documents.first
          .isFavorite,
      isFalse, // trở lại như cũ
    );
  });

  test('markOpened cập nhật lastOpenedAt trong state', () async {
    final (ProviderContainer container, _) = await _boot(
      docs: <DocumentItem>[_doc('a')],
    );
    await container.read(documentsControllerProvider.notifier).markOpened('a');
    expect(
      container.read(documentsControllerProvider).value!.documents.first
          .lastOpenedAt,
      isNotNull,
    );
  });
}
