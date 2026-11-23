/// Bỏ token khỏi URL và tải lại app để AuthGate quyết định trang chủ/login.
library;

import 'package:web/web.dart' as web;

void reloadSharedApp() {
  web.window.history.replaceState(null, '', web.window.location.pathname);
  web.window.location.reload();
}
