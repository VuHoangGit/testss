/// Entity chia sẻ link công khai + bình luận ghim vị trí (SRS).
library;

/// Một link chia sẻ của tài liệu (góc nhìn chủ tài liệu).
class ShareLink {
  const ShareLink({
    required this.id,
    required this.permission,
    required this.isActive,
    required this.viewCount,
    required this.createdAt,
    this.expiresAt,
    this.shareUrl = '',
  });

  final String id;

  /// 'view' | 'comment'.
  final String permission;

  final bool isActive;

  final int viewCount;

  /// URL đầy đủ — chỉ có ở lần tạo (server không lưu raw token).
  final String shareUrl;

  final DateTime createdAt;

  /// null = không hết hạn.
  final DateTime? expiresAt;

  /// Link còn dùng được không (đang hoạt động + chưa hết hạn).
  bool get isUsable => isActive && !isExpired;

  bool get isExpired {
    final DateTime? e = expiresAt;
    return e != null && e.isBefore(DateTime.now());
  }

  /// Nhãn trạng thái cho dialog quản lý link (FR-1.4).
  String get statusLabel {
    if (!isActive) return 'Đã thu hồi';
    if (isExpired) return 'Đã hết hạn';
    return 'Đang hoạt động';
  }
}

/// Metadata tài liệu trả về cho người nhận link (không có id nội bộ).
class SharedDocumentMeta {
  const SharedDocumentMeta({
    required this.fileName,
    required this.mimeType,
    required this.sizeBytes,
    required this.permission,
    required this.ownerName,
    this.pageCount,
    this.expiresAt,
  });

  final String fileName;
  final String mimeType;
  final int sizeBytes;
  final int? pageCount;

  /// 'view' | 'comment'.
  final String permission;

  final DateTime? expiresAt;
  final String ownerName;

  bool get canComment => permission == 'comment';
}

/// Một bình luận ghim vị trí trên trang PDF.
class SharedComment {
  const SharedComment({
    required this.id,
    required this.pageNumber,
    required this.normX,
    required this.normY,
    required this.authorName,
    required this.body,
    required this.createdAt,
    this.parentId,
    this.isPinned = true,
  });

  final String id;

  /// null = comment gốc; có giá trị = reply 1 cấp.
  final String? parentId;

  /// 1-based.
  final int pageNumber;

  /// Tọa độ chuẩn hóa [0,1] theo kích thước trang PDF.
  final double normX;
  final double normY;

  /// false = thread chung không vẽ chấm lên PDF (FR-4.8).
  final bool isPinned;

  final String authorName;
  final String body;
  final DateTime createdAt;
}

/// Comment ở góc nhìn chủ tài liệu — kèm share của link nào.
class OwnerSharedComment extends SharedComment {
  const OwnerSharedComment({
    required this.shareId,
    required super.id,
    required super.pageNumber,
    required super.normX,
    required super.normY,
    required super.authorName,
    required super.body,
    required super.createdAt,
    super.parentId,
    super.isPinned,
  });

  final String shareId;
}

/// Thông tin cần tạo link mới.
class CreateShareRequest {
  const CreateShareRequest({
    required this.permission,
    this.expiresInHours,
    this.expiresLabel = 'Không hết hạn',
  });

  /// 'view' | 'comment'.
  final String permission;

  /// null = không hết hạn; 24 / 168 / 720.
  final int? expiresInHours;

  /// Nhãn UI đi kèm lựa chọn thời hạn.
  final String expiresLabel;
}
