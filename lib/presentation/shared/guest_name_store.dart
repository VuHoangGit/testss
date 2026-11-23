/// Chọn kho lưu tên khách theo nền tảng; không thêm dependency mới.
library;

export 'guest_name_store_stub.dart'
    if (dart.library.io) 'guest_name_store_io.dart'
    if (dart.library.js_interop) 'guest_name_store_web.dart';
