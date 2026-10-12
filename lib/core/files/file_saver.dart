/// Lưu bytes ra "nơi người dùng thấy được": đĩa (desktop/mobile) hoặc
/// tải xuống trình duyệt (web). Nền tảng chọn file sẽ đổi implementation.
library;

export 'file_saver_io.dart' if (dart.library.html) 'file_saver_web.dart';
