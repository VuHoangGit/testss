/// Cài đặt AuthRepository bằng Supabase Auth (Google + email/password).
///
/// Phiên (access/refresh token) do supabase_flutter tự giữ (localStorage trên
/// web), tự refresh và đồng bộ giữa các tab. Repository chỉ bọc đăng nhập và
/// dựng AuthSession với profile lấy từ backend /auth/me (id đúng user local).
library;

import 'package:dio/dio.dart';
import 'package:supabase_flutter/supabase_flutter.dart' as supabase;

import '../../core/error/exceptions.dart';
import '../../core/network/dio_error_mapper.dart';
import '../../core/network/supabase_auth_error_mapper.dart';
import '../../domain/entities/user.dart';
import '../../domain/repositories/auth_repository.dart';
import '../models/models.dart';

class SupabaseAuthRepository implements AuthRepository {
  SupabaseAuthRepository({required this.dio});

  /// Dio "trần" (không interceptor) — gọi /auth/me sau khi có token.
  final Dio dio;

  supabase.GoTrueClient get _auth => supabase.Supabase.instance.client.auth;

  @override
  String? get cachedAccessToken => _auth.currentSession?.accessToken;

  @override
  Stream<AuthSession?> get sessionChanged =>
      _auth.onAuthStateChange.asyncMap((supabase.AuthState _) async {
        final supabase.Session? session = _auth.currentSession;
        if (session == null) return null;
        return await _profileOrClaims(session);
      });

  @override
  Future<AuthSession?> currentSession() async {
    final supabase.Session? session = _auth.currentSession;
    if (session == null) return null;
    return _profileOrClaims(session);
  }

  @override
  Future<void> register({
    required String email,
    required String password,
    String? name,
  }) async {
    final supabase.AuthResponse res;
    try {
      res = await _auth.signUp(
        email: email,
        password: password,
        data: <String, dynamic>{
          if (name != null && name.isNotEmpty) 'full_name': name,
        },
      );
    } on supabase.AuthException catch (e) {
      throw mapSupabaseAuthError(e.message);
    }
    // Supabase bật "Confirm email": đăng ký xong CHƯA có phiên — phải vào
    // hộp thư bấm link xác nhận rồi mới đăng nhập được. Ném lỗi riêng để UI
    // hướng dẫn đúng thay vì "Account created, please sign in" gây hiểu lầm.
    if (res.session == null) {
      throw const AuthException(
        'Account created — open your inbox and click the confirmation link before signing in',
        needsEmailConfirmation: true,
      );
    }
    // "Confirm email" TẮT: signUp trả luôn phiên. Nghiệp vụ yêu cầu đăng ký
    // xong phải quay về form đăng nhập, nên đồng bộ hồ sơ vào DB ngay (để thông
    // tin tài khoản nằm thật trong bảng users) rồi đăng xuất local — không để
    // SDK tự đưa người dùng vào app khi chưa đăng nhập lần nào.
    try {
      await _fetchProfile(res.session!.accessToken);
    } on Exception {
      // Đồng bộ lỗi không làm hỏng việc đăng ký: tài khoản đã tạo trên Supabase,
      // hồ sơ local sẽ được tạo ở lần đăng nhập đầu tiên (xem [login]).
    }
    await clearLocal();
  }

  @override
  Future<AuthSession> login({
    required String email,
    required String password,
  }) async {
    try {
      await _auth.signInWithPassword(email: email, password: password);
    } on supabase.AuthException catch (e) {
      throw mapSupabaseAuthError(e.message);
    }
    final supabase.Session? session = _auth.currentSession;
    if (session == null) {
      throw const AuthException('Sign-in did not create a session — try again');
    }
    // Đăng nhập chỉ được coi là thành công khi backend trả về user local — chính
    // lời gọi /auth/me này tạo/ cập nhật row trong bảng users. Trước đây lỗi ở
    // bước này bị nuốt rồi rơi về claims của token, nên app mở ra mà DB không có
    // user nào (và người dùng bị đá về login ngay sau đó).
    try {
      return await _fetchProfileWithRetry(session.accessToken);
    } on AuthException catch (e) {
      // Backend từ chối token (API trỏ sai project Supabase, JWKS lỗi...) → bỏ
      // phiên vừa tạo để không kẹt ở trạng thái "nửa đăng nhập".
      await clearLocal();
      throw AuthException('${e.message} — the server rejected this session');
    } on NetworkException {
      // Không lưu được hồ sơ thì cũng bỏ phiên: giữ lại sẽ cho người dùng vào app
      // trong khi thông tin tài khoản chưa nằm trong DB.
      await clearLocal();
      rethrow;
    }
  }

  /// Gọi /auth/me, thử lại khi lỗi mạng tạm thời (backend vừa restart, máy vừa
  /// ngủ dậy, tab vừa được focus lại). Lỗi xác thực (401) KHÔNG thử lại.
  ///
  /// Message lỗi cuối cùng có kèm địa chỉ API đang dùng: rất hay gặp trường hợp
  /// địa chỉ server lưu trong localStorage (nút "Server…" ở màn Login) trỏ vào
  /// IP/port cũ nên app báo "Could not connect" mà không rõ đang gọi đi đâu.
  Future<AuthSession> _fetchProfileWithRetry(String accessToken) async {
    const List<Duration> backoff = <Duration>[
      Duration(milliseconds: 300),
      Duration(milliseconds: 900),
    ];
    for (int attempt = 0; ; attempt++) {
      try {
        return await _fetchProfile(accessToken);
      } on NetworkException {
        if (attempt >= backoff.length) {
          throw NetworkException(
            'Could not connect to ${dio.options.baseUrl} — start the API server '
            '(uvicorn app.main:app --port 8000) and check the "Server…" address '
            'on the sign-in screen',
          );
        }
        await Future<void>.delayed(backoff[attempt]);
      }
    }
  }

  @override
  Future<void> signInWithGoogle() async {
    try {
      await _auth.signInWithOAuth(
        supabase.OAuthProvider.google,
        // Supabase xử lý consent Google rồi redirect về app; phiên về qua
        // sessionChanged (interceptor/controller không tự đoán).
        redirectTo: _redirectTarget,
      );
    } on supabase.AuthException catch (e) {
      throw mapSupabaseAuthError(e.message);
    }
  }

  @override
  Future<void> sendPasswordReset(String email) async {
    try {
      await _auth.resetPasswordForEmail(
        email,
        // Link trong email quay về app — Supabase exchange token rồi phát
        // event passwordRecovery kèm phiên (bắt qua passwordRecoveryChanged).
        redirectTo: _redirectTarget,
      );
    } on supabase.AuthException catch (e) {
      throw mapSupabaseAuthError(e.message);
    }
  }

  @override
  Future<void> updatePassword(String password) async {
    try {
      await _auth.updateUser(supabase.UserAttributes(password: password));
    } on supabase.AuthException catch (e) {
      throw mapSupabaseAuthError(e.message);
    }
  }

  @override
  Future<AuthSession> updateDisplayName(String name) async {
    final supabase.Session? session = _auth.currentSession;
    if (session == null) {
      throw const AuthException('No active session');
    }
    // PATCH /auth/me đánh dấu name_chosen_at + lưu tên vào bảng users; response
    // là profile mới nên state dùng lại được ngay, không cần gọi thêm lần nữa.
    try {
      final Response<dynamic> res = await dio.patch<dynamic>(
        '/auth/me',
        data: <String, dynamic>{'name': name},
        options: Options(
          headers: <String, String>{
            'Authorization': 'Bearer ${session.accessToken}',
          },
        ),
      );
      final Object? data = res.data;
      if (data is Map<String, dynamic>) {
        return AuthSession(
          user: UserModel.fromJson(data).toEntity(),
          accessToken: session.accessToken,
        );
      }
      throw const NetworkException('Unexpected server response format');
    } on DioException catch (e) {
      throw mapDioException(e);
    }
  }

  @override
  Stream<bool> get passwordRecoveryChanged => _auth.onAuthStateChange
      .map(
        (supabase.AuthState state) =>
            state.event == supabase.AuthChangeEvent.passwordRecovery,
      )
      .where((bool isRecovery) => isRecovery);

  @override
  Future<AuthSession> refreshSession() async {
    if (_auth.currentSession == null) {
      throw const AuthException('No active session');
    }
    try {
      await _auth.refreshSession();
    } on supabase.AuthException catch (e) {
      throw mapSupabaseAuthError(e.message);
    }
    final supabase.Session? session = _auth.currentSession;
    if (session == null) {
      throw const AuthException('The session has expired');
    }
    return _profileOrClaims(session);
  }

  @override
  Future<void> logout() async {
    try {
      await _auth.signOut();
    } on supabase.AuthException {
      // Offline/lỗi Supabase — phiên local vẫn bị SDK bỏ; không kẹt UX
    }
  }

  @override
  Future<void> clearLocal() async {
    try {
      await _auth.signOut(scope: supabase.SignOutScope.local);
    } on supabase.AuthException {
      // Bỏ qua — mục tiêu chỉ là không còn phiên để dùng
    }
  }

  String get _redirectTarget {
    // Uri.base.origin trên web; ngoài web không có OAuth redirect cần giữ
    return _isWebOriginUsable ? Uri.base.origin : 'http://localhost:53123';
  }

  bool get _isWebOriginUsable => Uri.base.hasScheme && Uri.base.host.isNotEmpty;

  /// Ưu tiên profile từ backend (đúng id user local); backend không phản hồi
  /// thì dùng dữ liệu trong token để app vẫn vào được (offline-friendly).
  Future<AuthSession> _profileOrClaims(supabase.Session session) async {
    try {
      return await _fetchProfile(session.accessToken);
    } on Exception {
      return _sessionFromClaims(session);
    }
  }

  Future<AuthSession> _fetchProfile(String accessToken) async {
    try {
      final Response<dynamic> res = await dio.get<dynamic>(
        '/auth/me',
        options: Options(
          headers: <String, String>{'Authorization': 'Bearer $accessToken'},
        ),
      );
      final Object? data = res.data;
      if (data is Map<String, dynamic>) {
        return AuthSession(
          user: UserModel.fromJson(data).toEntity(),
          accessToken: accessToken,
        );
      }
      throw const NetworkException('Unexpected server response format');
    } on DioException catch (e) {
      throw mapDioException(e);
    }
  }

  AuthSession _sessionFromClaims(supabase.Session session) {
    final supabase.User u = session.user;
    final Map<String, dynamic>? meta = u.userMetadata;
    final Object? name = meta?['full_name'] ?? meta?['name'];
    final Object? avatar = meta?['avatar_url'] ?? meta?['picture'];
    return AuthSession(
      user: User(
        id: u.id,
        email: u.email ?? '',
        name: name is String ? name : null,
        avatarUrl: avatar is String ? avatar : null,
      ),
      accessToken: session.accessToken,
    );
  }

}
