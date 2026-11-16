/// Widget test tab Tài liệu: hiển thị danh sách từ fake repository.
library;

import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:testss/domain/entities/document_entities.dart';
import 'package:testss/domain/repositories/documents_repository.dart';
import 'package:testss/presentation/documents/documents_providers.dart';
import 'package:testss/presentation/documents/documents_screen.dart';

class _FakeDocumentsRepository implements DocumentsRepository {
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
  Future<List<DocumentFolder>> listFolders() async => <DocumentFolder>[
    const DocumentFolder(id: 'f1', name: 'Hợp đồng', documentCount: 1),
  ];

  final DocumentItem _sample = DocumentItem(
    id: 'd1',
    name: 'hop-dong.pdf',
    mimeType: 'application/pdf',
    sizeBytes: 2048,
    pageCount: 3,
    folderId: 'f1',
    createdAt: DateTime.fromMillisecondsSinceEpoch(0),
  );

  @override
  Future<List<DocumentItem>> listDocuments({
    String? folderId,
    String? search,
    bool favoritesOnly = false,
    DocumentsSort sort = DocumentsSort.created,
  }) async => <DocumentItem>[_sample];

  @override
  Future<DocumentItem> setFavorite(
    String documentId, {
    required bool favorite,
  }) async => _sample.copyWith(isFavorite: favorite);

  @override
  Future<DocumentItem> markOpened(String documentId) async =>
      _sample.copyWith(lastOpenedAt: DateTime.fromMillisecondsSinceEpoch(1));

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

  @override
  Future<List<DocumentVersionItem>> listVersions(String documentId) =>
      throw UnimplementedError();

  @override
  Future<DocumentItem> uploadNewVersion({
    required String documentId,
    required String fileName,
    required Uint8List bytes,
    String label = '',
    void Function(int sent, int total)? onProgress,
  }) => throw UnimplementedError();

  @override
  Future<DocumentItem> restoreVersion({
    required String documentId,
    required String versionId,
  }) => throw UnimplementedError();

  @override
  Future<void> deleteVersion({
    required String documentId,
    required String versionId,
  }) => throw UnimplementedError();

  @override
  Future<VersionDiffResult> diffVersions({
    required String documentId,
    required String oldVersionId,
    String? newVersionId,
  }) => throw UnimplementedError();
}

Future<void> _pump(WidgetTester tester) async {
  await tester.pumpWidget(
    ProviderScope(
      overrides: [
        documentsRepositoryProvider.overrideWithValue(
          _FakeDocumentsRepository(),
        ),
      ],
      child: const MaterialApp(home: Scaffold(body: DocumentsScreen())),
    ),
  );
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('hiện toolbar, chip thư mục và danh sách tài liệu', (
    WidgetTester tester,
  ) async {
    await _pump(tester);
    expect(find.text('Upload'), findsOneWidget);
    expect(find.text('New folder'), findsOneWidget);
    expect(find.textContaining('Hợp đồng'), findsWidgets);
    expect(find.text('hop-dong.pdf'), findsOneWidget);
    // UI đã đổi sang tiếng Anh (commit eaeeed7) — card hiện "3 pages · 2 KB"
    expect(find.textContaining('3 pages'), findsOneWidget);
  });

  testWidgets('bật chế độ chọn để gộp hiện nút Gộp', (
    WidgetTester tester,
  ) async {
    await _pump(tester);
    await tester.tap(find.text('Select to merge'));
    await tester.pumpAndSettle();
    expect(find.text('Merge (0)'), findsOneWidget);
    expect(find.text('Cancel selection'), findsOneWidget);
  });
}
