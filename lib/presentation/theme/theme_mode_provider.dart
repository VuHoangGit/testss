/// Chế độ sáng/tối của app — Riverpod Notifier, lưu localStorage (web).
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'theme_storage.dart';

final NotifierProvider<ThemeModeController, ThemeMode> themeModeProvider =
    NotifierProvider<ThemeModeController, ThemeMode>(ThemeModeController.new);

class ThemeModeController extends Notifier<ThemeMode> {
  @override
  ThemeMode build() {
    return switch (readSavedTheme()) {
      'light' => ThemeMode.light,
      'dark' => ThemeMode.dark,
      _ => ThemeMode.system,
    };
  }

  void setMode(ThemeMode mode) {
    state = mode;
    writeSavedTheme(switch (mode) {
      ThemeMode.light => 'light',
      ThemeMode.dark => 'dark',
      ThemeMode.system => 'system',
    });
  }

  /// Đảo sáng ↔ tối so với chế độ HIỆN TẠI (kể cả khi đang theo hệ thống).
  void toggle(Brightness platformBrightness) {
    final Brightness current = effectiveBrightness(platformBrightness);
    setMode(
      current == Brightness.dark ? ThemeMode.light : ThemeMode.dark,
    );
  }

  Brightness effectiveBrightness(Brightness platformBrightness) {
    if (state == ThemeMode.system) return platformBrightness;
    return state == ThemeMode.dark ? Brightness.dark : Brightness.light;
  }
}
