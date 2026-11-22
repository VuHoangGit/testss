import 'package:flutter_test/flutter_test.dart';
import 'package:docvaultproject/core/config/app_config.dart';

void main() {
  group('AppConfig.normalizeServerUrl', () {
    test('thiếu scheme → thêm http:// và ghép /api/v1', () {
      expect(
        AppConfig.normalizeServerUrl('192.168.1.5:8000'),
        'http://192.168.1.5:8000/api/v1',
      );
    });

    test('có path thừa → chỉ giữ scheme://host:port/api/v1', () {
      expect(
        AppConfig.normalizeServerUrl('http://10.0.0.3:8000/documents'),
        'http://10.0.0.3:8000/api/v1',
      );
    });

    test('đã có /api/v1 → giữ nguyên', () {
      expect(
        AppConfig.normalizeServerUrl('http://192.168.1.5:8000/api/v1'),
        'http://192.168.1.5:8000/api/v1',
      );
    });

    test('https không port → giữ scheme, bỏ port', () {
      expect(
        AppConfig.normalizeServerUrl('https://docs.example.com'),
        'https://docs.example.com/api/v1',
      );
    });

    test('rỗng → FormatException', () {
      expect(
        () => AppConfig.normalizeServerUrl('   '),
        throwsFormatException,
      );
    });

    test('scheme khác http(s) → FormatException', () {
      expect(
        () => AppConfig.normalizeServerUrl('ftp://192.168.1.5'),
        throwsFormatException,
      );
    });

    test('không phải địa chỉ → FormatException', () {
      expect(
        () => AppConfig.normalizeServerUrl('not a url'),
        throwsFormatException,
      );
    });
  });
}
