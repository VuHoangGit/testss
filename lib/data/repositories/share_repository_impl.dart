/// Cài đặt ShareRepository bằng Dio: nhóm owner dùng Dio có auth, nhóm public
/// dùng Dio riêng KHÔNG gắn interceptor Supabase (người nhận không có phiên).
library;

import 'dart:typed_data';

import 'package:dio/dio.dart';

import '../../core/network/api_client.dart';
import '../../core/network/dio_error_mapper.dart';
import '../../domain/entities/share_entities.dart';
import '../../domain/repositories/share_repository.dart';

class ShareRepositoryImpl implements ShareRepository {
  ShareRepositoryImpl({Dio? publicDio, required this._authDio})
    : _publicDio = publicDio ?? buildDio();

  final Dio _publicDio;
  final Dio _authDio;

  DateTime _parseDate(dynamic value) =>
      value == null ? DateTime.now() : DateTime.parse(value as String);

  // -- Nhóm chủ tài liệu ----------------------------------------------------

  @override
  Future<ShareLink> createShare(
    String documentId, {
    required String permission,
    int? expiresInHours,
  }) async {
    try {
      final Response<dynamic> res = await _authDio.post<dynamic>(
        '/documents/$documentId/shares',
        data: <String, dynamic>{
          'permission': permission,
          'expires_in_hours': ?expiresInHours,
        },
      );
      return _shareFromJson(res.data as Map<String, dynamic>);
    } on DioException catch (e) {
      throw mapDioException(e, fallback: 'Không tạo được link chia sẻ');
    }
  }

  @override
  Future<List<ShareLink>> listShares(String documentId) async {
    try {
      final Response<dynamic> res = await _authDio.get<dynamic>(
        '/documents/$documentId/shares',
      );
      final List<dynamic> items = res.data as List<dynamic>? ?? <dynamic>[];
      return items
          .map((dynamic e) => _shareFromJson(e as Map<String, dynamic>))
          .toList(growable: false);
    } on DioException catch (e) {
      throw mapDioException(e, fallback: 'Không tải được danh sách link');
    }
  }

  @override
  Future<void> revokeShare(String documentId, String shareId) async {
    try {
      await _authDio.delete<dynamic>('/documents/$documentId/shares/$shareId');
    } on DioException catch (e) {
      throw mapDioException(e, fallback: 'Không thu hồi được link');
    }
  }

  @override
  Future<List<OwnerSharedComment>> listOwnerComments(String documentId) async {
    try {
      final Response<dynamic> res = await _authDio.get<dynamic>(
        '/documents/$documentId/share-comments',
      );
      final List<dynamic> items = res.data as List<dynamic>? ?? <dynamic>[];
      return items
          .map((dynamic e) => _ownerCommentFromJson(e as Map<String, dynamic>))
          .toList(growable: false);
    } on DioException catch (e) {
      throw mapDioException(e, fallback: 'Không tải được bình luận chia sẻ');
    }
  }

  @override
  Future<void> deleteOwnerComment(String documentId, String commentId) async {
    try {
      await _authDio.delete<dynamic>(
        '/documents/$documentId/share-comments/$commentId',
      );
    } on DioException catch (e) {
      throw mapDioException(e, fallback: 'Không xóa được bình luận');
    }
  }

  // -- Nhóm public ----------------------------------------------------------

  @override
  Future<SharedDocumentMeta> getSharedMeta(String token) async {
    try {
      final Response<dynamic> res = await _publicDio.get<dynamic>(
        '/public/shares/$token',
      );
      final Map<String, dynamic> json = res.data as Map<String, dynamic>;
      return SharedDocumentMeta(
        fileName: json['file_name'] as String? ?? '',
        mimeType: json['mime_type'] as String? ?? 'application/octet-stream',
        sizeBytes: (json['size_bytes'] as num?)?.toInt() ?? 0,
        pageCount: (json['page_count'] as num?)?.toInt(),
        permission: json['permission'] as String? ?? 'view',
        expiresAt: json['expires_at'] == null
            ? null
            : DateTime.parse(json['expires_at'] as String),
        ownerName: json['owner_name'] as String? ?? '',
      );
    } on DioException catch (e) {
      throw mapDioException(e, fallback: 'Không tải được tài liệu');
    }
  }

  @override
  Future<Uint8List> downloadSharedFile(String token) async {
    try {
      final Response<List<int>> res = await _publicDio.get<List<int>>(
        '/public/shares/$token/file',
        options: Options(responseType: ResponseType.bytes),
      );
      return Uint8List.fromList(res.data ?? <int>[]);
    } on DioException catch (e) {
      throw mapDioException(e, fallback: 'Không tải được tài liệu');
    }
  }

  @override
  Future<List<SharedComment>> listComments(String token) async {
    try {
      final Response<dynamic> res = await _publicDio.get<dynamic>(
        '/public/shares/$token/comments',
      );
      final List<dynamic> items = res.data as List<dynamic>? ?? <dynamic>[];
      return items
          .map((dynamic e) => _commentFromJson(e as Map<String, dynamic>))
          .toList(growable: false);
    } on DioException catch (e) {
      throw mapDioException(e, fallback: 'Không tải được bình luận');
    }
  }

  @override
  Future<SharedComment> addComment(
    String token, {
    required int pageNumber,
    required double normX,
    required double normY,
    required String authorName,
    required String body,
    String? parentId,
    bool isPinned = true,
  }) async {
    try {
      final Response<dynamic> res = await _publicDio.post<dynamic>(
        '/public/shares/$token/comments',
        data: <String, dynamic>{
          'page_number': pageNumber,
          'norm_x': normX,
          'norm_y': normY,
          'author_name': authorName,
          'body': body,
          'parent_id': ?parentId,
          'is_pinned': isPinned,
        },
      );
      return _commentFromJson(res.data as Map<String, dynamic>);
    } on DioException catch (e) {
      throw mapDioException(e, fallback: 'Không gửi được bình luận');
    }
  }

  // -- Parse ----------------------------------------------------------------

  ShareLink _shareFromJson(Map<String, dynamic> json) => ShareLink(
    id: json['id'] as String,
    permission: json['permission'] as String? ?? 'view',
    expiresAt: json['expires_at'] == null
        ? null
        : _parseDate(json['expires_at']),
    isActive: json['is_active'] as bool? ?? false,
    viewCount: (json['view_count'] as num?)?.toInt() ?? 0,
    shareUrl: json['share_url'] as String? ?? '',
    createdAt: _parseDate(json['created_at']),
  );

  SharedComment _commentFromJson(Map<String, dynamic> json) => SharedComment(
    id: json['id'] as String,
    parentId: json['parent_id'] as String?,
    pageNumber: (json['page_number'] as num).toInt(),
    normX: (json['norm_x'] as num).toDouble(),
    normY: (json['norm_y'] as num).toDouble(),
    isPinned: json['is_pinned'] as bool? ?? true,
    authorName: json['author_name'] as String? ?? 'Khách',
    body: json['body'] as String? ?? '',
    createdAt: _parseDate(json['created_at']),
  );

  OwnerSharedComment _ownerCommentFromJson(Map<String, dynamic> json) =>
      OwnerSharedComment(
        shareId: json['share_id'] as String,
        id: json['id'] as String,
        parentId: json['parent_id'] as String?,
        pageNumber: (json['page_number'] as num).toInt(),
        normX: (json['norm_x'] as num).toDouble(),
        normY: (json['norm_y'] as num).toDouble(),
        isPinned: json['is_pinned'] as bool? ?? true,
        authorName: json['author_name'] as String? ?? 'Khách',
        body: json['body'] as String? ?? '',
        createdAt: _parseDate(json['created_at']),
      );
}
