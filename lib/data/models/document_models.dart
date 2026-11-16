/// Model JSON cho folders/documents — backend trả snake_case (Sprint 2).
library;

import '../../domain/entities/document_entities.dart';

class DocumentItemModel extends DocumentItem {
  const DocumentItemModel({
    required super.id,
    required super.name,
    required super.mimeType,
    required super.sizeBytes,
    required super.createdAt,
    super.folderId,
    super.pageCount,
    super.isFavorite,
    super.lastOpenedAt,
  });

  factory DocumentItemModel.fromJson(Map<String, dynamic> json) {
    return DocumentItemModel(
      id: json['id'] as String,
      name: json['original_name'] as String,
      mimeType: (json['mime_type'] as String?) ?? 'application/octet-stream',
      sizeBytes: (json['size_bytes'] as num?)?.toInt() ?? 0,
      pageCount: (json['page_count'] as num?)?.toInt(),
      folderId: json['folder_id'] as String?,
      isFavorite: (json['is_favorite'] as bool?) ?? false,
      lastOpenedAt: json['last_opened_at'] == null
          ? null
          : DateTime.parse(json['last_opened_at'] as String),
      createdAt: DateTime.parse(json['created_at'] as String),
    );
  }
}

class DocumentFolderModel extends DocumentFolder {
  const DocumentFolderModel({
    required super.id,
    required super.name,
    required super.documentCount,
  });

  factory DocumentFolderModel.fromJson(Map<String, dynamic> json) {
    return DocumentFolderModel(
      id: json['id'] as String,
      name: json['name'] as String,
      documentCount: (json['document_count'] as num?)?.toInt() ?? 0,
    );
  }
}

/// Model JSON cho một bản cũ trong lịch sử phiên bản.
class DocumentVersionItemModel extends DocumentVersionItem {
  const DocumentVersionItemModel({
    required super.id,
    required super.versionNumber,
    required super.sizeBytes,
    required super.uploadedAt,
    super.pageCount,
    super.label,
  });

  factory DocumentVersionItemModel.fromJson(Map<String, dynamic> json) {
    return DocumentVersionItemModel(
      id: json['id'] as String,
      versionNumber: (json['version_number'] as num?)?.toInt() ?? 0,
      sizeBytes: (json['size_bytes'] as num?)?.toInt() ?? 0,
      pageCount: (json['page_count'] as num?)?.toInt(),
      label: (json['label'] as String?) ?? '',
      uploadedAt: DateTime.parse(json['created_at'] as String),
    );
  }
}

/// Model JSON cho kết quả so sánh 2 phiên bản.
class VersionDiffResultModel extends VersionDiffResult {
  const VersionDiffResultModel({
    required super.diffLines,
    required super.addedCount,
    required super.removedCount,
    super.aiSummary,
  });

  factory VersionDiffResultModel.fromJson(Map<String, dynamic> json) {
    return VersionDiffResultModel(
      diffLines: (json['diff'] as List<dynamic>? ?? const <dynamic>[])
          .map((dynamic e) => e as String)
          .toList(growable: false),
      addedCount: (json['added'] as num?)?.toInt() ?? 0,
      removedCount: (json['removed'] as num?)?.toInt() ?? 0,
      aiSummary: json['ai_summary'] as String?,
    );
  }
}
