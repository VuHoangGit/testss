/// Entity tài liệu & thư mục (Sprint 2) — thuần dữ liệu, không phụ thuộc tầng dưới.
library;

class DocumentItem {
  const DocumentItem({
    required this.id,
    required this.name,
    required this.mimeType,
    required this.sizeBytes,
    required this.createdAt,
    this.folderId,
    this.pageCount,
  });

  final String id;
  final String name;
  final String mimeType;
  final int sizeBytes;
  final int? pageCount;
  final String? folderId;
  final DateTime createdAt;

  bool get isPdf => mimeType == 'application/pdf';
}

class DocumentFolder {
  const DocumentFolder({
    required this.id,
    required this.name,
    required this.documentCount,
  });

  final String id;
  final String name;
  final int documentCount;
}
