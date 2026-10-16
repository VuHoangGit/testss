import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
import 'package:testss/core/error/exceptions.dart';
import 'package:testss/core/network/dio_error_mapper.dart';
import 'package:testss/core/storage/token_storage.dart';
import 'package:testss/data/repositories/auth_repository_impl.dart';

import '../helpers.dart';

class _MockDio extends Mock implements Dio {}

class _FakeStorage implements TokenStorage {
  String? access;
  String? refresh;
  bool cleared = false;

  @override
  Future<void> clear() async {
    cleared = true;
    access = null;
    refresh = null;
  }

  @override
  Future<(String?, String?)> read() async => (access, refresh);

  @override
  Future<void> save({required String accessToken, required String refreshToken}) async {
    access = accessToken;
    refresh = refreshToken;
  }
}

Response<dynamic> _res(Map<String, dynamic> json) => Response<dynamic>(
      requestOptions: RequestOptions(path: 'x'),
      data: json,
    );

void main() {
  late _MockDio dio;
  late _FakeStorage storage;
  late AuthRepositoryImpl repo;

  final Map<String, dynamic> tokenJson = <String, dynamic>{
    'access_token': makeJwt(<String, dynamic>{
      'sub': 'u-1', 'sid': 's-1', 'email': 'a@gmail.com', 'name': 'An',
      'exp': DateTime.now().millisecondsSinceEpoch ~/ 1000 + 600,
    }),
    'refresh_token': 'refresh-abc-1234567890',
    'user': <String, dynamic>{
      'id': 'u-1', 'email': 'a@gmail.com', 'name': 'An', 'avatar_url': null,
    },
  };

  setUp(() {
    dio = _MockDio();
    storage = _FakeStorage();
    repo = AuthRepositoryImpl(dio: dio, storage: storage);
  });

  test('devLogin → lưu token + trả session đúng user', () async {
    when(() => dio.post<dynamic>('/auth/dev',
            data: any(named: 'data')))
        .thenAnswer((Invocation _) async => _res(tokenJson));

    final session = await repo.devLogin(email: 'a@gmail.com', name: 'An');

    expect(session.user.email, 'a@gmail.com');
    expect(session.accessToken, tokenJson['access_token']);
    expect(storage.access, tokenJson['access_token']);
    expect(repo.cachedAccessToken, tokenJson['access_token']);
  });

  test('restore: access còn hạn → khôi phục offline, KHÔNG gọi mạng', () async {
    storage.access = tokenJson['access_token'];
    storage.refresh = 'r-1';

    final session = await repo.restore();

    expect(session, isNotNull);
    expect(session!.user.email, 'a@gmail.com');
    verifyNever(() => dio.post<dynamic>(any(), data: any(named: 'data')));
  });

  test('restore: access hết hạn + refresh OK → vào app với token mới', () async {
    storage.access = makeJwt(<String, dynamic>{
      'sub': 'u-1', 'email': 'a@gmail.com',
      'exp': DateTime.now().millisecondsSinceEpoch ~/ 1000 - 100,
    });
    storage.refresh = 'r-1';
    when(() => dio.post<dynamic>('/auth/refresh',
            data: any(named: 'data')))
        .thenAnswer((Invocation _) async => _res(tokenJson));

    final session = await repo.restore();

    expect(session!.accessToken, tokenJson['access_token']);
    expect(storage.refresh, tokenJson['refresh_token']); // đã ghi đè token mới
  });

  test('restore: refresh 401 (phiên chết) → dọn local + về Login (EC-12)', () async {
    storage.access = makeJwt(<String, dynamic>{
      'sub': 'u-1', 'email': 'a@gmail.com',
      'exp': DateTime.now().millisecondsSinceEpoch ~/ 1000 - 100,
    });
    storage.refresh = 'r-1';
    when(() => dio.post<dynamic>('/auth/refresh',
            data: any(named: 'data')))
        .thenThrow(
      DioException(requestOptions: RequestOptions(path: ''), response:
          Response<dynamic>(requestOptions: RequestOptions(path: ''),
              statusCode: 401, data: <String, dynamic>{'detail': 'hết hạn'})),
    );

    final session = await repo.restore();

    expect(session, isNull);
    expect(storage.cleared, isTrue);
    expect(storage.access, isNull);
  });

  test('logout: revoke server OK → xóa local (EC-18/20)', () async {
    storage.access = tokenJson['access_token'];
    storage.refresh = 'r-1';
    when(() => dio.post<dynamic>('/auth/logout',
            options: any(named: 'options')))
        .thenAnswer((Invocation _) async =>
            _res(<String, dynamic>{'detail': 'Đã đăng xuất'}));

    await repo.logout();

    expect(storage.cleared, isTrue);
    expect(repo.cachedAccessToken, isNull);
  });

  test('logout: backend chết (NetworkException) → vẫn xóa local (EC-18)', () async {
    storage.access = tokenJson['access_token'];
    storage.refresh = 'r-1';
    when(() => dio.post<dynamic>('/auth/logout',
            options: any(named: 'options')))
        .thenThrow(DioException(
      requestOptions: RequestOptions(path: ''),
      type: DioExceptionType.connectionError,
    ));

    await repo.logout();
    expect(storage.cleared, isTrue);
  });

  test('mapDioException: 401 → AuthException kèm detail tiếng Việt', () {
    final Exception e = mapDioException(DioException(
      requestOptions: RequestOptions(path: ''),
      response: Response<dynamic>(
        requestOptions: RequestOptions(path: ''),
        statusCode: 401,
        data: <String, dynamic>{'detail': 'Phiên đăng nhập không hợp lệ'},
      ),
    ));
    expect(e, isA<AuthException>());
    expect((e as AuthException).message, contains('Phiên'));
  });

  test('mapDioException: connectionError → NetworkException (EC-16)', () {
    final Exception e = mapDioException(DioException(
      requestOptions: RequestOptions(path: ''),
      type: DioExceptionType.connectionError,
    ));
    expect(e, isA<NetworkException>());
  });

  test('mapDioException: 5xx → NetworkException (EC-16)', () {
    final Exception e = mapDioException(DioException(
      requestOptions: RequestOptions(path: ''),
      response: Response<dynamic>(
        requestOptions: RequestOptions(path: ''),
        statusCode: 503,
      ),
    ));
    expect(e, isA<NetworkException>());
  });

  test('login email/mật khẩu → POST /auth/login + lưu token', () async {
    when(() => dio.post<dynamic>('/auth/login', data: any(named: 'data')))
        .thenAnswer((Invocation _) async => _res(tokenJson));

    final session = await repo.login(email: 'a@gmail.com', password: '123456');

    expect(session.user.email, 'a@gmail.com');
    expect(storage.access, tokenJson['access_token']);
    expect(repo.cachedAccessToken, tokenJson['access_token']);
  });

  test('login sai mật khẩu 401 → AuthException kèm detail server', () async {
    when(() => dio.post<dynamic>('/auth/login', data: any(named: 'data')))
        .thenThrow(DioException(
      requestOptions: RequestOptions(path: ''),
      response: Response<dynamic>(
        requestOptions: RequestOptions(path: ''),
        statusCode: 401,
        data: <String, dynamic>{'detail': 'Email hoặc mật khẩu không đúng'},
      ),
    ));

    await expectLater(
      repo.login(email: 'a@gmail.com', password: '999999'),
      throwsA(isA<AuthException>()
          .having((AuthException e) => e.message, 'message', 'Email hoặc mật khẩu không đúng')),
    );
    expect(storage.access, isNull);
  });

  test('register → POST /auth/register, KHÔNG lưu token', () async {
    when(() => dio.post<dynamic>('/auth/register', data: any(named: 'data')))
        .thenAnswer((Invocation _) async => _res(<String, dynamic>{
              'message': 'Đăng ký thành công. Hãy đăng nhập.',
              'email': 'a@gmail.com',
            }));

    await repo.register(email: 'a@gmail.com', password: '123456');

    expect(storage.access, isNull);
    expect(repo.cachedAccessToken, isNull);
  });

  test('register trùng email 409 → AuthException kèm detail server', () async {
    when(() => dio.post<dynamic>('/auth/register', data: any(named: 'data')))
        .thenThrow(DioException(
      requestOptions: RequestOptions(path: ''),
      response: Response<dynamic>(
        requestOptions: RequestOptions(path: ''),
        statusCode: 409,
        data: <String, dynamic>{'detail': 'Email đã được đăng ký'},
      ),
    ));

    await expectLater(
      repo.register(email: 'a@gmail.com', password: '123456'),
      throwsA(isA<AuthException>()
          .having((AuthException e) => e.message, 'message', 'Email đã được đăng ký')),
    );
  });
}
