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
