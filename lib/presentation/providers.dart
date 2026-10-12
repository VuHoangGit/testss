/// DI trung tâm: mọi provider của app khai báo ở đây (thay codegen cho gọn).
library;

import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/network/api_client.dart';
import '../core/network/auth_interceptor.dart';
import '../core/storage/token_storage.dart';
import '../data/repositories/auth_repository_impl.dart';
import '../domain/entities/user.dart';
import '../domain/repositories/auth_repository.dart';
import 'auth/auth_controller.dart';

final Provider<TokenStorage> tokenStorageProvider =
    Provider<TokenStorage>((Ref ref) => SecureTokenStorage());

final Provider<Dio> plainDioProvider =
    Provider<Dio>((Ref ref) => buildDio());

final Provider<AuthRepository> authRepositoryProvider =
    Provider<AuthRepository>(
  (Ref ref) => AuthRepositoryImpl(
    dio: ref.watch(plainDioProvider),
    storage: ref.watch(tokenStorageProvider),
  ),
);

/// Dio cho API nghiệp vụ: tự gắn token + single-flight refresh khi 401.
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
    authControllerProvider =
    AsyncNotifierProvider<AuthController, AuthSession?>(AuthController.new);
