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
