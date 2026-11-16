/// Test parse JSON cho model lịch sử phiên bản + kết quả so sánh.
library;

import 'package:flutter_test/flutter_test.dart';

import 'package:testss/data/models/document_models.dart';

void main() {
  test('DocumentVersionItemModel đọc đúng field snake_case từ backend', () {
    final DocumentVersionItemModel model = DocumentVersionItemModel.fromJson(
      <String, dynamic>{
        'id': 'v-id-1',
        'document_id': 'doc-1',
        'version_number': 2,
        'size_bytes': 2048,
        'page_count': 5,
        'label': 'client edited clause 4',
        'created_at': '2026-11-13T08:30:00Z',
      },
    );
    expect(model.id, 'v-id-1');
    expect(model.versionNumber, 2);
    expect(model.sizeBytes, 2048);
    expect(model.pageCount, 5);
    expect(model.label, 'client edited clause 4');
    expect(model.uploadedAt, DateTime.parse('2026-11-13T08:30:00Z'));
  });

  test('thiếu page_count/label thì dùng mặc định an toàn', () {
    final DocumentVersionItemModel model = DocumentVersionItemModel.fromJson(
      <String, dynamic>{
        'id': 'v-id-2',
        'document_id': 'doc-1',
        'version_number': 1,
        'size_bytes': 100,
        'created_at': '2026-11-13T08:30:00Z',
      },
    );
    expect(model.pageCount, isNull);
    expect(model.label, '');
  });

  test('VersionDiffResultModel đọc diff + thống kê + tóm tắt AI', () {
    final VersionDiffResultModel model = VersionDiffResultModel.fromJson(
      <String, dynamic>{
        'diff': <String>['-dong hai', '+dong ba'],
        'added': 1,
        'removed': 1,
        'ai_summary': '- Điều 4 đổi số tiền',
      },
    );
    expect(model.diffLines, <String>['-dong hai', '+dong ba']);
    expect(model.addedCount, 1);
    expect(model.removedCount, 1);
    expect(model.aiSummary, '- Điều 4 đổi số tiền');
  });

  test('hai bản giống nhau: diff rỗng + ai_summary null', () {
    final VersionDiffResultModel model = VersionDiffResultModel.fromJson(
      <String, dynamic>{'diff': <String>[], 'added': 0, 'removed': 0},
    );
    expect(model.diffLines, isEmpty);
    expect(model.aiSummary, isNull);
  });
}
