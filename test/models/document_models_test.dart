/// Test map JSON → model cho documents (Sprint 2).
library;

import 'package:flutter_test/flutter_test.dart';
import 'package:docvaultproject/data/models/document_models.dart';

void main() {
  test('DocumentItemModel.fromJson map đủ field', () {
    final model = DocumentItemModel.fromJson(<String, dynamic>{
      'id': 'doc-1',
      'original_name': 'bao-cao.pdf',
      'mime_type': 'application/pdf',
      'size_bytes': 2048,
      'page_count': 7,
      'folder_id': 'folder-1',
      'created_at': '2026-10-12T03:00:00Z',
    });
    expect(model.id, 'doc-1');
    expect(model.name, 'bao-cao.pdf');
    expect(model.isPdf, isTrue);
    expect(model.pageCount, 7);
    expect(model.folderId, 'folder-1');
    expect(model.sizeBytes, 2048);
  });

  test('DocumentItemModel chấp nhận null folder/pageCount (file thường)', () {
    final model = DocumentItemModel.fromJson(<String, dynamic>{
      'id': 'doc-2',
      'original_name': 'anh.png',
      'mime_type': 'image/png',
      'size_bytes': 10,
      'page_count': null,
      'folder_id': null,
      'created_at': '2026-10-12T03:00:00Z',
    });
    expect(model.isPdf, isFalse);
    expect(model.pageCount, isNull);
    expect(model.folderId, isNull);
  });

  test('DocumentFolderModel.fromJson map document_count', () {
    final model = DocumentFolderModel.fromJson(<String, dynamic>{
      'id': 'f1',
      'name': 'Tai chinh',
      'document_count': 4,
    });
    expect(model.name, 'Tai chinh');
    expect(model.documentCount, 4);
  });
}
