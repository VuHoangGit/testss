/// Chọn bản storage theo nền: web dùng localStorage, nền khác no-op.
library;

export 'theme_storage_stub.dart'
    if (dart.library.js_interop) 'theme_storage_web.dart';
