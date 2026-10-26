/// DI trung tâm: mọi provider của app khai báo ở đây (thay codegen cho gọn).
library;

import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/network/api_client.dart';
import '../core/network/auth_interceptor.dart';
import '../data/repositories/auth_repository_impl.dart';
import '../domain/entities/user.dart';
import '../domain/repositories/auth_repository.dart';
import 'auth/auth_controller.dart';

final Provider<Dio> plainDioProvider = Provider<Dio>((Ref ref) => buildDio());

/// Repository auth trên Supabase — phiên do supabase_flutter tự giữ.
final Provider<AuthRepository> authRepositoryProvider =
    Provider<AuthRepository>(
      (Ref ref) => SupabaseAuthRepository(dio: ref.watch(plainDioProvider)),
    );

/// Dio cho API nghiệp vụ: tự gắn token + refresh khi 401.
final Provider<Dio> apiDioProvider = Provider<Dio>((Ref ref) {
  final AuthRepository repo = ref.watch(authRepositoryProvider);
  final Dio dio = buildDio();
  dio.interceptors.add(
    AuthInterceptor(
      dio: dio,
      getAccessToken: () => repo.cachedAccessToken,
      refresh: repo.refreshSession,
      onSessionExpired: () =>
          ref.read(authControllerProvider.notifier).forceSignOut(),
    ),
  );
  return dio;
});

final AsyncNotifierProvider<AuthController, AuthSession?>
authControllerProvider = AsyncNotifierProvider<AuthController, AuthSession?>(
  AuthController.new,
);
