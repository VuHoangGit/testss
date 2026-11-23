/// Về trang chủ từ link public: bỏ token rồi tải lại app (web).
library;

import '../../main.dart' show initialShareToken;
import 'share_navigation_stub.dart'
    if (dart.library.js_interop) 'share_navigation_web.dart' as platform;

void clearShareLinkAndGoHome() {
  initialShareToken = null;
  platform.reloadSharedApp();
}
