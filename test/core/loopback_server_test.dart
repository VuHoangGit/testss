import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:testss/core/auth/loopback_oauth_server.dart';
import 'package:testss/core/error/exceptions.dart';

void main() {
  test('start → port động; nhận code+state đúng; server tự đóng', () async {
    final LoopbackOAuthServer server = LoopbackOAuthServer();
    await server.start();
    expect(server.isRunning, isTrue);
    expect(server.port, greaterThan(0));

    final Future<String> waiting =
        server.waitForCode(expectedState: 'st-123', timeout: const Duration(seconds: 5));

    // Giả lập Google redirect về loopback
    final HttpClient client = HttpClient();
    await client
        .getUrl(Uri.parse('http://127.0.0.1:${server.port}/?code=abc-1&state=st-123'))
        .then((HttpClientRequest req) => req.close());
    client.close();

    expect(await waiting, 'abc-1');
    expect(server.isRunning, isFalse); // finally stop
  });

  test('state không khớp (CSRF) → StateError', () async {
    final LoopbackOAuthServer server = LoopbackOAuthServer();
    await server.start();

    final Future<String> waiting =
        server.waitForCode(expectedState: 'expected', timeout: const Duration(seconds: 5));

    final HttpClient client = HttpClient();
    await client
        .getUrl(Uri.parse('http://127.0.0.1:${server.port}/?code=x&state=SAI'))
        .then((HttpClientRequest req) => req.close());
    client.close();

    await expectLater(waiting, throwsStateError);
  });

  test('Google trả error=access_denied → AuthException (EC-04)', () async {
    final LoopbackOAuthServer server = LoopbackOAuthServer();
    await server.start();

    final Future<String> waiting =
        server.waitForCode(expectedState: 's', timeout: const Duration(seconds: 5));

    final HttpClient client = HttpClient();
    await client
        .getUrl(Uri.parse('http://127.0.0.1:${server.port}/?error=access_denied'))
        .then((HttpClientRequest req) => req.close());
    client.close();

    await expectLater(waiting, throwsA(isA<AuthException>()));
  });

  test('không ai redirect trong timeout → AuthException hết giờ (EC-24)', () async {
    final LoopbackOAuthServer server = LoopbackOAuthServer();
    await server.start();

    await expectLater(
      server.waitForCode(expectedState: 's', timeout: const Duration(milliseconds: 150)),
      throwsA(isA<AuthException>()),
    );
    expect(server.isRunning, isFalse);
  });
}
