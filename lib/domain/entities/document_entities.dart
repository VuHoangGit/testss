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
    this.isFavorite = false,
    this.lastOpenedAt,
  });

  final String id;
  final String name;
  final String mimeType;
  final int sizeBytes;
  final int? pageCount;
  final String? folderId;
  final DateTime createdAt;

  /// Đã gắn sao (TOOLS → Favorites) — true nếu user đánh dấu từ menu file.
  final bool isFavorite;

  /// Lần mở gần nhất (TOOLS → Recent); null = chưa từng mở.
  final DateTime? lastOpenedAt;

  /// Bản sao với vài trường đổi (dùng cho optimistic update sau toggle sao/mở).
  DocumentItem copyWith({bool? isFavorite, DateTime? lastOpenedAt}) =>
      DocumentItem(
        id: id,
        name: name,
        mimeType: mimeType,
        sizeBytes: sizeBytes,
        createdAt: createdAt,
        folderId: folderId,
        pageCount: pageCount,
        isFavorite: isFavorite ?? this.isFavorite,
        lastOpenedAt: lastOpenedAt ?? this.lastOpenedAt,
      );

  /// Đuôi file văn bản thuần — khớp danh sách backend dùng để trích text
  /// (client-uploader có thể gửi mime `application/octet-stream`).
  static const List<String> _textExtensions = <String>[
    '.txt',
    '.md',
    '.markdown',
    '.csv',
    '.json',
    '.log',
    '.xml',
    '.yml',
    '.yaml',
    '.py',
    '.js',
    '.ts',
    '.dart',
    '.java',
    '.c',
    '.cpp',
    '.html',
    '.css',
    '.ini',
  ];

  bool get isPdf => mimeType == 'application/pdf';

  bool get isWordDoc =>
      mimeType ==
      'application/vnd.openxmlformats-officedocument.wordprocessingml.document';

  bool get isImage => mimeType.startsWith('image/');

  bool get isTextFile =>
      mimeType.startsWith('text/') ||
      _textExtensions.any((String ext) => name.toLowerCase().endsWith(ext));

  /// Có thể trích văn bản (PDF/Word/txt/md...) để xem dạng text + dịch.
  bool get hasTextContent => isPdf || isWordDoc || isTextFile;

  /// Mọi file upload đều mở được: text-like xem nội dung, ảnh xem hình.
  bool get isViewable => hasTextContent || isImage;
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

/// Một bản cũ trong lịch sử phiên bản của tài liệu.
class DocumentVersionItem {
  const DocumentVersionItem({
    required this.id,
    required this.versionNumber,
    required this.sizeBytes,
    required this.uploadedAt,
    this.pageCount,
    this.label = '',
  });

  final String id;

  /// 1 = bản gần nhất bị thay thế, 2 = cũ hơn...
  final int versionNumber;
  final int sizeBytes;

  /// Ghi chú người dùng nhập khi upload bản mới (vd "sau khi khách sửa điều 4").
  final String label;
  final int? pageCount;
  final DateTime uploadedAt;
}

/// Kết quả so sánh 2 phiên bản: diff dòng + thống kê + tóm tắt AI.
class VersionDiffResult {
  const VersionDiffResult({
    required this.diffLines,
    required this.addedCount,
    required this.removedCount,
    this.aiSummary,
  });

  final List<String> diffLines;
  final int addedCount;
  final int removedCount;

  /// Tóm tắt thay đổi bằng AI (tiếng Việt); null = 2 bản giống nhau.
  final String? aiSummary;
}

