/// Provider cho chia sẻ link + SharedView (SRS) — Dio public KHÔNG auth.
library;

import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show FutureProviderFamily;

import '../../core/config/app_config.dart';
import '../../core/network/api_client.dart';
import '../../data/repositories/share_repository_impl.dart';
import '../../domain/entities/share_entities.dart';
import '../../domain/repositories/share_repository.dart';
import '../providers.dart';

/// Dio cho API public /public/shares/... — không gắn interceptor Supabase
/// (người nhận không có phiên; tránh đính token vào request công khai).
final Provider<Dio> publicShareDioProvider = Provider<Dio>(
  (Ref ref) => buildDio(baseUrl: AppConfig.publicShareApiBaseUrl),
);

final Provider<ShareRepository> shareRepositoryProvider =
    Provider<ShareRepository>((Ref ref) {
      return ShareRepositoryImpl(
        publicDio: ref.watch(publicShareDioProvider),
        authDio: ref.watch(apiDioProvider),
      );
    });

/// Cache theo documentId: rebuild menu không tạo request mới liên tục.
final FutureProviderFamily<int, String> shareCommentCountProvider =
    FutureProvider.family<int, String>((Ref ref, String documentId) async {
      final List<OwnerSharedComment> comments = await ref
          .watch(shareRepositoryProvider)
          .listOwnerComments(documentId);
      return comments.length;
    });
