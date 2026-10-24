/// Cài đặt AuthRepository: Dio (endpoint auth, không interceptor để tránh đệ quy)
/// + flutter_securestorage. Refresh token chỉ đi qua đây, không lộ ra UI.
library;

import 'package:dio/dio.dart';
import 'package:jwt_decoder/jwt_decoder.dart';

import '../../core/error/exceptions.dart';
import '../../core/network/dio_error_mapper.dart';
import '../../core/storage/token_storage.dart';
import '../../core/auth/token_expiry.dart';
import '../../domain/entities/user.dart';
import '../../domain/repositories/auth_repository.dart';
import '../models/models.dart';

class AuthRepositoryImpl implements AuthRepository {
  AuthRepositoryImpl({required this.dio, required this.storage});

  final Dio dio;
  final TokenStorage storage;
  String? _accessToken;
  String? _refreshToken;

  @override
  String? get cachedAccessToken => _accessToken;

  @override
  Future<AuthSession> devLogin({required String email, String? name}) async {
    try {
      final Response<dynamic> res = await dio.post<dynamic>(
        '/auth/dev',
        data: <String, dynamic>{'email': email, 'name': name},
      );
      return await _persist(TokenResponseModel.fromJson(_map(res)));
    } on DioException catch (e) {
      throw mapDioException(e);
    }
  }

  @override
  Future<void> register({
    required String email,
    required String password,
    String? name,
  }) async {
    try {
      await dio.post<dynamic>(
        '/auth/register',
        data: <String, dynamic>{
          'email': email,
          'password': password,
          'name': name,
        },
      );
    } on DioException catch (e) {
      // 409 → detail "Email đã được đăng ký" từ server (mapDioException xử lý)
      throw mapDioException(e);
    }
  }

  @override
  Future<AuthSession> login({
    required String email,
    required String password,
  }) async {
    try {
      final Response<dynamic> res = await dio.post<dynamic>(
        '/auth/login',
        data: <String, dynamic>{'email': email, 'password': password},
      );
      return await _persist(TokenResponseModel.fromJson(_map(res)));
    } on DioException catch (e) {
      throw mapDioException(e);
    }
  }

  @override
  Future<AuthSession?> restore() async {
    final (String? access, String? refresh) = await storage.read();
    _accessToken = access;
    _refreshToken = refresh;
    if (access == null || refresh == null) return null;
    if (isAccessTokenUsable(access)) {
      return _sessionFromTokens(access, refresh);
    }
    try {
      return await refreshSession();
    } on AuthException {
      // Refresh chết (hết hạn/thu hồi) → dọn local, về màn đăng nhập (EC-12)
      await clearLocal();
      return null;
    } on NetworkException {
      // Backend không liên lạc được → vẫn vào app với token cũ;
      // request API đầu tiên sẽ thử refresh lại (EC-16)
      return _sessionFromTokens(access, refresh);
    }
  }

  @override
  Future<AuthSession> refreshSession() async {
    final String? refresh = _refreshToken;
    if (refresh == null) {
      throw const AuthException('Chưa có phiên đăng nhập');
    }
    try {
      final Response<dynamic> res = await dio.post<dynamic>(
        '/auth/refresh',
        data: <String, dynamic>{'refresh_token': refresh},
      );
      final Map<String, dynamic> data = _map(res);
      final String accessToken = data['access_token'] as String;
      final String refreshToken = data['refresh_token'] as String;
      _accessToken = accessToken;
      _refreshToken = refreshToken;
      await storage.save(accessToken: accessToken, refreshToken: refreshToken);
      return _sessionFromTokens(accessToken, refreshToken);
    } on DioException catch (e) {
      throw mapDioException(e);
    }
  }

  @override
  Future<void> logout() async {
    try {
      await _revokeCurrentSession();
    } on AuthException {
      // Access hết hạn → refresh rồi thử revoke đúng 1 lần nữa; vẫn fail thì
      // chấp nhận: session tự chết theo expires_at (EC-18)
      try {
        await refreshSession();
        await _revokeCurrentSession();
      } on Exception {
        // bỏ qua
      }
    } on NetworkException {
      // Offline — vẫn xóa local, không kẹt UX (EC-18)
    }
    await clearLocal();
  }

  @override
  Future<void> clearLocal() async {
    _accessToken = null;
    _refreshToken = null;
    await storage.clear();
  }

  Future<void> _revokeCurrentSession() async {
    final String? access = _accessToken;
    if (access == null) return;
    await dio.post<dynamic>(
      '/auth/logout',
      options: Options(
        headers: <String, String>{'Authorization': 'Bearer $access'},
        receiveTimeout: const Duration(seconds: 3),
      ),
    );
  }

  Future<AuthSession> _persist(TokenResponseModel model) async {
    _accessToken = model.accessToken;
    _refreshToken = model.refreshToken;
    await storage.save(
      accessToken: model.accessToken,
      refreshToken: model.refreshToken,
    );
    return AuthSession(
      user: model.user.toEntity(),
      accessToken: model.accessToken,
      refreshToken: model.refreshToken,
    );
  }

  AuthSession _sessionFromTokens(String access, String refresh) {
    final Map<String, dynamic> claims = JwtDecoder.decode(access);
    final User user = User(
      id: (claims['sub'] ?? '') as String,
      email: (claims['email'] ?? '') as String,
      name: claims['name'] as String?,
      avatarUrl: claims['picture'] as String?,
    );
    return AuthSession(user: user, accessToken: access, refreshToken: refresh);
  }

  Map<String, dynamic> _map(Response<dynamic> res) {
    final Object? data = res.data;
    if (data is Map<String, dynamic>) return data;
    throw const NetworkException('Phản hồi máy chủ không đúng định dạng');
  }
}
