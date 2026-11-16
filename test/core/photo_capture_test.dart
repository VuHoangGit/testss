/// Test đặt tên file cho ảnh chụp: backend chọn MIME theo đuôi file nên đuôi
/// phải luôn nằm trong danh sách cho phép.
library;

import 'package:flutter_test/flutter_test.dart';

import 'package:testss/core/capture/photo_capture.dart';

void main() {
  final DateTime at = DateTime(2026, 11, 22, 10, 15, 30);

  test('giữ đuôi ảnh gốc và thêm mốc thời gian', () {
    expect(
      scanFileName(name: 'IMG_2026.JPG', at: at),
      'scan_20261122_101530.jpg',
    );
    expect(
      scanFileName(name: 'page.png', at: at),
      'scan_20261122_101530.png',
    );
  });

  test('đuôi lạ (HEIC/WEBP) → jpg vì image_picker đã nén lại sang JPEG', () {
    expect(
      scanFileName(name: 'IMG_0001.HEIC', at: at),
      'scan_20261122_101530.jpg',
    );
    expect(
      scanFileName(name: 'photo.webp', at: at),
      'scan_20261122_101530.jpg',
    );
  });

  test('không có đuôi thì đoán theo MIME, không rõ thì jpg', () {
    expect(
      scanFileName(name: 'blob', mimeType: 'image/png', at: at),
      'scan_20261122_101530.png',
    );
    expect(
      scanFileName(name: 'blob', mimeType: 'image/jpeg', at: at),
      'scan_20261122_101530.jpg',
    );
    expect(scanFileName(name: 'blob', at: at), 'scan_20261122_101530.jpg');
    expect(scanFileName(at: at), 'scan_20261122_101530.jpg');
  });

  test('giờ chụp được đệm 0 cho đủ 2 chữ số', () {
    expect(
      scanFileName(name: 'page.jpg', at: DateTime(2026, 1, 2, 3, 4, 5)),
      'scan_20260102_030405.jpg',
    );
  });
}
