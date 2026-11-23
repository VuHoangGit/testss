/// Hợp đồng tầng domain cho chia sẻ link + bình luận (SRS).
library;

import 'dart:typed_data';

import '../entities/share_entities.dart';

abstract interface class ShareRepository {
  // -- Nhóm chủ tài liệu (đăng nhập) --------------------------------------

  /// Tạo link mới; trả kèm URL đầy đủ (raw token chỉ hiện lần này).
  Future<ShareLink> createShare(
    String documentId, {
    required String permission,
    int? expiresInHours,
  });

  /// Mọi link của tài liệu (gồm đã thu hồi/hết hạn).
  Future<List<ShareLink>> listShares(String documentId);

  /// Thu hồi link — link chết ngay.
  Future<void> revokeShare(String documentId, String shareId);

  /// Mọi comment của mọi link thuộc tài liệu (FR-6.5).
  Future<List<OwnerSharedComment>> listOwnerComments(String documentId);

  /// Xóa comment bất kỳ với tư cách chủ tài liệu.
  Future<void> deleteOwnerComment(String documentId, String commentId);

  // -- Nhóm public (không đăng nhập, theo token) --------------------------

  /// Metadata tài liệu từ token; token sai → ném Exception 404.
  Future<SharedDocumentMeta> getSharedMeta(String token);

  /// Tải nội dung file từ token.
  Future<Uint8List> downloadSharedFile(String token);

  /// Toàn bộ comment của link.
  Future<List<SharedComment>> listComments(String token);

  /// Thêm comment. Link chỉ xem → server trả 403.
  Future<SharedComment> addComment(
    String token, {
    required int pageNumber,
    required double normX,
    required double normY,
    required String authorName,
    required String body,
    String? parentId,
    bool isPinned = true,
  });
}
