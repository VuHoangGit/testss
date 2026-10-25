/// Nút gạt sáng/tối trên app bar — đảo chế độ và nhớ lựa chọn.
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'theme_mode_provider.dart';

class ThemeToggleButton extends ConsumerWidget {
  const ThemeToggleButton({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    // Watch để icon cập nhật ngay khi đổi chế độ.
    ref.watch(themeModeProvider);
    final ThemeModeController controller = ref.read(themeModeProvider.notifier);
    final Brightness platform = MediaQuery.platformBrightnessOf(context);
    final bool isDark =
        controller.effectiveBrightness(platform) == Brightness.dark;

    return IconButton(
      tooltip: isDark ? 'Chuyển sang chế độ sáng' : 'Chuyển sang chế độ tối',
      onPressed: () => controller.toggle(platform),
      icon: Icon(isDark ? Icons.light_mode_outlined : Icons.dark_mode_outlined),
    );
  }
}
