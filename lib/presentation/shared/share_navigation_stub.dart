import '../../core/navigation/root_navigator_key.dart';
import '../../main.dart' show AuthGate;

import 'package:flutter/material.dart';

/// Nền không web: thay màn public bằng AuthGate, phiên đăng nhập vẫn được giữ.
void reloadSharedApp() {
  final BuildContext? context = rootNavigatorKey.currentContext;
  if (context == null) return;
  Navigator.of(context).pushAndRemoveUntil<void>(
    MaterialPageRoute<void>(builder: (_) => const AuthGate()),
    (_) => false,
  );
}
