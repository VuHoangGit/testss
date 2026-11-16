/// Cài đặt DocumentsRepository bằng Dio gọi backend FastAPI (Sprint 2).
///
/// Mọi DioException được map qua [mapDioException]: 401/403 → AuthException,
/// mạng/5xx → NetworkException (EC-16), còn lại giữ detail tiếng Việt.
library;

import 'dart:typed_data';

import 'package:dio/dio.dart';

import '../../core/network/dio_error_mapper.dart';
import '../../domain/entities/document_entities.dart';
import '../../domain/repositories/documents_repository.dart';
import '../models/document_models.dart';

class DocumentsRepositoryImpl implements DocumentsRepository {
  DocumentsRepositoryImpl({required this.dio});

  final Dio dio;

  @override
  Future<List<DocumentFolder>> listFolders() async {
    try {
      final Response<dynamic> res = await dio.get<dynamic>('/folders');
      final List<dynamic> items =
          (res.data as List<dynamic>? ?? const <dynamic>[]);
      return items
          .map(
            (dynamic e) =>
                DocumentFolderModel.fromJson(e as Map<String, dynamic>),
          )
          .toList(growable: false);
    } on DioException catch (e) {
      throw mapDioException(e, fallback: 'Could not load folders');
    }
  }

  @override
  Future<DocumentFolder> createFolder(String name) async {
    try {
      final Response<dynamic> res = await dio.post<dynamic>(
        '/folders',
        data: <String, String>{'name': name},
      );
      return DocumentFolderModel.fromJson(res.data as Map<String, dynamic>);
    } on DioException catch (e) {
      throw mapDioException(e, fallback: 'Could not create the folder');
    }
  }

  @override
  Future<void> deleteFolder(String folderId) async {
    try {
      await dio.delete<dynamic>('/folders/$folderId');
    } on DioException catch (e) {
      throw mapDioException(e, fallback: 'Could not delete the folder');
    }
  }

  @override
  Future<List<DocumentItem>> listDocuments({
    String? folderId,
    String? search,
    bool favoritesOnly = false,
    DocumentsSort sort = DocumentsSort.created,
  }) async {
    final Map<String, String> query = <String, String>{
      'folder_id': ?folderId,
      if (search != null && search.trim().isNotEmpty) 'search': search.trim(),
      if (favoritesOnly) 'favorites_only': 'true',
      if (sort == DocumentsSort.recent) 'sort': 'recent',
    };
    try {
      final Response<dynamic> res = await dio.get<dynamic>(
        '/documents',
        queryParameters: query.isEmpty ? null : query,
      );
      final List<dynamic> items =
          (res.data as List<dynamic>? ?? const <dynamic>[]);
      return items
          .map(
            (dynamic e) =>
                DocumentItemModel.fromJson(e as Map<String, dynamic>),
          )
          .toList(growable: false);
    } on DioException catch (e) {
      throw mapDioException(e, fallback: 'Could not load documents');
    }
  }

  @override
  Future<DocumentItem> setFavorite(
    String documentId, {
    required bool favorite,
  }) async {
    try {
      final Response<dynamic> res = await dio.patch<dynamic>(
        '/documents/$documentId/favorite',
        data: <String, bool>{'favorite': favorite},
      );
      return DocumentItemModel.fromJson(res.data as Map<String, dynamic>);
    } on DioException catch (e) {
      throw mapDioException(e, fallback: 'Could not update the favorite');
    }
  }

  @override
  Future<DocumentItem> markOpened(String documentId) async {
    try {
      final Response<dynamic> res = await dio.post<dynamic>(
        '/documents/$documentId/open',
      );
      return DocumentItemModel.fromJson(res.data as Map<String, dynamic>);
    } on DioException catch (e) {
      throw mapDioException(e, fallback: 'Could not mark the document as opened');
    }
  }

  @override
  Future<DocumentItem> uploadDocument({
    required String fileName,
    required Uint8List bytes,
    String? folderId,
    void Function(int sent, int total)? onProgress,
  }) async {
    try {
      final FormData form = FormData.fromMap(<String, dynamic>{
        'folder_id': ?folderId,
        'file': MultipartFile.fromBytes(
          bytes,
          filename: fileName,
          contentType: _mediaType(fileName),
        ),
      });
      final Response<dynamic> res = await dio.post<dynamic>(
        '/documents',
        data: form,
        onSendProgress: onProgress,
      );
      return DocumentItemModel.fromJson(res.data as Map<String, dynamic>);
    } on DioException catch (e) {
      throw mapDioException(e, fallback: 'Could not upload the file');
    }
  }

  @override
  Future<Uint8List> downloadDocument(String documentId) async {
    try {
      final Response<List<int>> res = await dio.get<List<int>>(
        '/documents/$documentId/download',
        options: Options(responseType: ResponseType.bytes),
      );
      return Uint8List.fromList(res.data ?? <int>[]);
    } on DioException catch (e) {
      throw mapDioException(e, fallback: 'Could not download the document');
    }
  }

  @override
  Future<void> deleteDocument(String documentId) async {
    try {
      await dio.delete<dynamic>('/documents/$documentId');
    } on DioException catch (e) {
      throw mapDioException(e, fallback: 'Could not delete the document');
    }
  }

  @override
  Future<DocumentItem> mergeDocuments({
    required List<String> documentIds,
    required String name,
  }) async {
    try {
      final Response<dynamic> res = await dio.post<dynamic>(
        '/documents/merge',
        data: <String, dynamic>{'document_ids': documentIds, 'name': name},
      );
      return DocumentItemModel.fromJson(res.data as Map<String, dynamic>);
    } on DioException catch (e) {
      throw mapDioException(e, fallback: 'Could not merge the documents');
    }
  }

  @override
  Future<List<DocumentItem>> splitDocument(
    String documentId, {
    required String ranges,
  }) async {
    try {
      final Response<dynamic> res = await dio.post<dynamic>(
        '/documents/$documentId/split',
        data: <String, dynamic>{'ranges': ranges},
      );
      final List<dynamic> items =
          (res.data as List<dynamic>? ?? const <dynamic>[]);
      return items
          .map(
            (dynamic e) =>
                DocumentItemModel.fromJson(e as Map<String, dynamic>),
          )
          .toList(growable: false);
    } on DioException catch (e) {
      throw mapDioException(e, fallback: 'Could not split the document');
    }
  }

  @override
  Future<DocumentItem> protectDocument(
    String documentId, {
    required String password,
  }) => _passwordAction(
    '/documents/$documentId/protect',
    documentId,
    password,
    fallback: 'Could not set the password',
  );

  @override
  Future<DocumentItem> unprotectDocument(
    String documentId, {
    required String password,
  }) => _passwordAction(
    '/documents/$documentId/unprotect',
    documentId,
    password,
    fallback: 'Could not remove the password',
  );

  Future<DocumentItem> _passwordAction(
    String path,
    String documentId,
    String password, {
    required String fallback,
  }) async {
    try {
      final Response<dynamic> res = await dio.post<dynamic>(
        path,
        data: <String, String>{'password': password},
      );
      return DocumentItemModel.fromJson(res.data as Map<String, dynamic>);
    } on DioException catch (e) {
      throw mapDioException(e, fallback: fallback);
    }
  }

  // -- Lịch sử phiên bản -------------------------------------------------

  @override
  Future<List<DocumentVersionItem>> listVersions(String documentId) async {
    try {
      final Response<dynamic> res = await dio.get<dynamic>(
        '/documents/$documentId/versions',
      );
      final List<dynamic> items =
          (res.data as List<dynamic>? ?? const <dynamic>[]);
      return items
          .map(
            (dynamic e) =>
                DocumentVersionItemModel.fromJson(e as Map<String, dynamic>),
          )
          .toList(growable: false);
    } on DioException catch (e) {
      throw mapDioException(e, fallback: 'Could not load the version history');
    }
  }

  @override
  Future<DocumentItem> uploadNewVersion({
    required String documentId,
    required String fileName,
    required Uint8List bytes,
    String label = '',
    void Function(int sent, int total)? onProgress,
  }) async {
    try {
      final FormData form = FormData.fromMap(<String, dynamic>{
        'label': label,
        'file': MultipartFile.fromBytes(
          bytes,
          filename: fileName,
          contentType: _mediaType(fileName),
        ),
      });
      final Response<dynamic> res = await dio.post<dynamic>(
        '/documents/$documentId/versions',
        data: form,
        onSendProgress: onProgress,
      );
      return DocumentItemModel.fromJson(res.data as Map<String, dynamic>);
    } on DioException catch (e) {
      throw mapDioException(e, fallback: 'Could not upload the new version');
    }
  }

  @override
  Future<DocumentItem> restoreVersion({
    required String documentId,
    required String versionId,
  }) async {
    try {
      final Response<dynamic> res = await dio.post<dynamic>(
        '/documents/$documentId/versions/$versionId/restore',
      );
      return DocumentItemModel.fromJson(res.data as Map<String, dynamic>);
    } on DioException catch (e) {
      throw mapDioException(e, fallback: 'Could not restore the version');
    }
  }

  @override
  Future<void> deleteVersion({
    required String documentId,
    required String versionId,
  }) async {
    try {
      await dio.delete<dynamic>(
        '/documents/$documentId/versions/$versionId',
      );
    } on DioException catch (e) {
      throw mapDioException(e, fallback: 'Could not delete the version');
    }
  }

  @override
  Future<VersionDiffResult> diffVersions({
    required String documentId,
    required String oldVersionId,
    String? newVersionId,
  }) async {
    try {
      final Response<dynamic> res = await dio.post<dynamic>(
        '/documents/$documentId/versions/diff',
        data: <String, dynamic>{
          'old_version_id': oldVersionId,
          'new_version_id': ?newVersionId,
        },
      );
      return VersionDiffResultModel.fromJson(res.data as Map<String, dynamic>);
    } on DioException catch (e) {
      throw mapDioException(e, fallback: 'Could not compare the versions');
    }
  }

  /// Map đuôi file → MIME để backend lưu đúng loại (quan trọng cho PDF).
  static DioMediaType _mediaType(String fileName) {
    final String ext = fileName.split('.').last.toLowerCase();
    const Map<String, String> map = <String, String>{
      'pdf': 'application/pdf',
      'png': 'image/png',
      'jpg': 'image/jpeg',
      'jpeg': 'image/jpeg',
      'gif': 'image/gif',
      'txt': 'text/plain',
      'md': 'text/markdown',
      'zip': 'application/zip',
      'doc': 'application/msword',
      'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
      'xls': 'application/vnd.ms-excel',
      'xlsx':
          'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      'ppt': 'application/vnd.ms-powerpoint',
      'pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
    };
    final String mime = map[ext] ?? 'application/octet-stream';
    final List<String> parts = mime.split('/');
    return DioMediaType(parts[0], parts[1]);
  }
}
