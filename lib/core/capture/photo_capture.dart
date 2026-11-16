/// Lấy ảnh tài liệu từ điện thoại: chụp bằng camera hoặc chọn ảnh có sẵn.
///
/// Luồng OCR ảnh: camera → bytes → upload thành tài liệu trong kho → OCR.
/// Tách thành interface để màn hình AI nhận bản giả trong widget test — plugin
/// `image_picker` cần camera thật nên không chạy được trong test.
library;

import 'dart:typed_data';

import 'package:flutter/services.dart'
    show MissingPluginException, PlatformException;
import 'package:image_picker/image_picker.dart';

/// Ảnh vừa lấy được: nội dung + tên file dùng làm tên tài liệu.
class CapturedPhoto {
  const CapturedPhoto({required this.bytes, required this.fileName});

  final Uint8List bytes;

  /// Tên file đã chuẩn hoá đuôi (xem [scanFileName]) — backend chọn MIME theo
  /// đuôi file nên đuôi phải nằm trong danh sách cho phép.
  final String fileName;
}

/// Lỗi có câu thông báo hiển thị thẳng cho người dùng (UI đang tiếng Anh).
class PhotoCaptureException implements Exception {
  const PhotoCaptureException(this.message);

  final String message;

  @override
  String toString() => message;
}

/// Nguồn ảnh cho OCR.
abstract interface class PhotoCapture {
  /// Mở camera sau và chụp một ảnh; null = người dùng huỷ.
  Future<CapturedPhoto?> takePhoto();

  /// Chọn một ảnh có sẵn trong máy; null = người dùng huỷ.
  Future<CapturedPhoto?> pickFromGallery();
}

/// Đuôi file backend chấp nhận cho ảnh (`ALLOWED_UPLOAD_TYPES`).
///
/// WebP/HEIC không nằm trong danh sách nên ảnh lạ được đổi tên thành `.jpg`:
/// `image_picker` đã nén lại (maxWidth + imageQuality) sang JPEG trước khi trả.
const Set<String> _allowedPhotoExtensions = <String>{'jpg', 'jpeg', 'png', 'gif'};

/// Tên file cho ảnh vừa lấy: `scan_20261122_101530.jpg`.
///
/// Giữ đuôi gốc nếu hợp lệ, còn lại đoán theo MIME rồi mặc định `.jpg`.
/// [at] chỉ dùng trong test (mặc định lấy giờ hiện tại).
String scanFileName({String? name, String? mimeType, DateTime? at}) {
  final DateTime stamp = at ?? DateTime.now();
  final String extension =
      _extensionOf(name) ?? _extensionForMime(mimeType) ?? 'jpg';
  final String date =
      '${stamp.year.toString().padLeft(4, '0')}'
      '${_twoDigits(stamp.month)}${_twoDigits(stamp.day)}';
  final String time =
      '${_twoDigits(stamp.hour)}${_twoDigits(stamp.minute)}'
      '${_twoDigits(stamp.second)}';
  return 'scan_${date}_$time.$extension';
}

String? _extensionOf(String? name) {
  if (name == null) return null;
  final int dot = name.lastIndexOf('.');
  if (dot < 0 || dot == name.length - 1) return null;
  final String extension = name.substring(dot + 1).toLowerCase();
  return _allowedPhotoExtensions.contains(extension) ? extension : null;
}

String? _extensionForMime(String? mimeType) {
  switch (mimeType?.toLowerCase()) {
    case 'image/png':
      return 'png';
    case 'image/gif':
      return 'gif';
    case 'image/jpeg':
    case 'image/jpg':
      return 'jpg';
    default:
      return null; // webp/heic/không rõ → jpg (xem _allowedPhotoExtensions)
  }
}

String _twoDigits(int value) => value.toString().padLeft(2, '0');

/// Cài đặt thật bằng `image_picker`.
///
/// Ảnh được thu về cạnh dài ≤ 2400px và nén JPEG ngay trên máy trước khi
/// upload: ảnh camera 12 MP nặng 4–8 MB, upload qua Wi-Fi LAN sẽ rất chậm mà
/// OCR chỉ cần ~2000px (server cũng cắt lại lần nữa).
class ImagePickerPhotoCapture implements PhotoCapture {
  const ImagePickerPhotoCapture();

  static const double _maxSidePixels = 2400;
  static const int _jpegQuality = 88;

  @override
  Future<CapturedPhoto?> takePhoto() => _pick(
    ImageSource.camera,
    // Camera sau: camera người dùng chĩa vào trang giấy.
    preferredCameraDevice: CameraDevice.rear,
  );

  @override
  Future<CapturedPhoto?> pickFromGallery() => _pick(ImageSource.gallery);

  Future<CapturedPhoto?> _pick(
    ImageSource source, {
    CameraDevice preferredCameraDevice = CameraDevice.rear,
  }) async {
    XFile? file;
    try {
      file = await ImagePicker().pickImage(
        source: source,
        preferredCameraDevice: preferredCameraDevice,
        maxWidth: _maxSidePixels,
        maxHeight: _maxSidePixels,
        imageQuality: _jpegQuality,
      );
    } on PlatformException catch (error) {
      throw PhotoCaptureException(_messageFor(source, error.code));
    } on MissingPluginException {
      throw PhotoCaptureException(_messageFor(source, 'no camera plugin'));
    } on UnimplementedError {
      // Desktop (Windows/Linux) không có camera trong plugin.
      throw PhotoCaptureException(_messageFor(source, 'unsupported platform'));
    }
    if (file == null) return null; // người dùng huỷ

    final Uint8List bytes;
    try {
      bytes = await file.readAsBytes();
    } on Exception catch (error) {
      throw PhotoCaptureException('Could not read the photo ($error).');
    }
    if (bytes.isEmpty) {
      throw const PhotoCaptureException('The photo is empty — try again.');
    }
    return CapturedPhoto(
      bytes: bytes,
      fileName: scanFileName(name: file.name, mimeType: file.mimeType),
    );
  }

  /// Camera thiếu quyền / máy không có camera → nói rõ đường đi tiếp theo.
  String _messageFor(ImageSource source, String reason) {
    if (source == ImageSource.gallery) {
      return 'Could not open the photo library ($reason). '
          'Check the app permissions and try again.';
    }
    return 'Could not open the camera ($reason). Allow camera access for this '
        'app, or use "Use a photo" to pick an existing picture.';
  }
}
