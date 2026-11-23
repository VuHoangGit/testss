/// Design system DocuVault — restyle theo ảnh mẫu: sidebar navy đậm cố định,
/// accent royal blue, nav item + nút dạng pill (bo tròn hết cỡ), card bo 18.
///
/// Material 3 nhưng không dùng default Material look: màu tự đặt (không seed),
/// border 1px, shadow nhẹ. Semantic color (success/warning/info/AI) expose
/// qua [AppColors] để các màn dùng chung, tránh hardcode màu rải rác.
library;

import 'package:flutter/material.dart';

/// Bảng màu cố định theo spec — light & dark semantic giống nhau.
class AppColors {
  AppColors._();

  // Brand — royal blue theo ảnh mẫu (thay indigo cũ)
  static const Color primary = Color(0xFF1D4ED8);
  static const Color primaryHover = Color(0xFF1E40AF);
  static const Color primaryLight = Color(0xFFEFF6FF);
  static const Color aiPrimary = Color(0xFF7C3AED);
  static const Color aiLight = Color(0xFFF5F3FF);

  // Sidebar navy đậm cố định cho cả light & dark (kiểu ảnh mẫu: rail tối,
  // vùng nội dung sáng — tương phản mạnh)
  static const Color sidebarBg = Color(0xFF0F172A);
  static const Color sidebarBorder = Color(0xFF243046);
  static const Color sidebarMuted = Color(0xFF9AA6BC);

  // Trạng thái
  static const Color success = Color(0xFF16A34A);
  static const Color warning = Color(0xFFD97706);
  static const Color error = Color(0xFFDC2626);
  static const Color info = Color(0xFF2563EB);

  // Light surface — trắng ngà lạnh theo ảnh mẫu
  static const Color lightBg = Color(0xFFF8FAFD);
  static const Color lightSurface = Color(0xFFFFFFFF);
  static const Color lightBorder = Color(0xFFE7EBF3);
  static const Color lightDivider = Color(0xFFEDF1F7);
  static const Color lightHeading = Color(0xFF0F172A);
  static const Color lightBody = Color(0xFF475569);
  static const Color lightMuted = Color(0xFF94A3B8);

  // Dark surface
  static const Color darkBg = Color(0xFF0F1115);
  static const Color darkSurface = Color(0xFF171A21);
  static const Color darkBorder = Color(0xFF262B36);
  static const Color darkDivider = Color(0xFF1F232C);
  static const Color darkHeading = Color(0xFFF3F4F6);
  static const Color darkBody = Color(0xFFB7BCC7);
  static const Color darkMuted = Color(0xFF7C8494);
}

class AppTheme {
  AppTheme._();

  static ThemeData light() {
    final ColorScheme scheme = ColorScheme.light(
      primary: AppColors.primary,
      onPrimary: Colors.white,
      primaryContainer: AppColors.primaryLight,
      onPrimaryContainer: AppColors.primaryHover,
      secondary: AppColors.aiPrimary,
      onSecondary: Colors.white,
      secondaryContainer: AppColors.aiLight,
      onSecondaryContainer: AppColors.aiPrimary,
      surface: AppColors.lightSurface,
      onSurface: AppColors.lightHeading,
      onSurfaceVariant: AppColors.lightBody,
      surfaceContainerHighest: const Color(0xFFEFF3FA),
      error: AppColors.error,
      onError: Colors.white,
      errorContainer: const Color(0xFFFEE2E2),
      onErrorContainer: AppColors.error,
      outline: AppColors.lightBorder,
      outlineVariant: AppColors.lightBorder,
    );
    return _base(scheme, AppColors.lightBg, AppColors.lightDivider);
  }

  static ThemeData dark() {
    final ColorScheme scheme = ColorScheme.dark(
      primary: const Color(0xFF7CA6F5),
      onPrimary: const Color(0xFF0A1830),
      primaryContainer: const Color(0xFF17274D),
      onPrimaryContainer: const Color(0xFFC3D7FB),
      secondary: AppColors.aiPrimary,
      onSecondary: Colors.white,
      secondaryContainer: const Color(0xFF33245E),
      onSecondaryContainer: const Color(0xFFDDD1FF),
      surface: AppColors.darkSurface,
      onSurface: AppColors.darkHeading,
      onSurfaceVariant: AppColors.darkBody,
      surfaceContainerHighest: const Color(0xFF20242E),
      error: const Color(0xFFF87171),
      onError: const Color(0xFF2B0B0B),
      errorContainer: const Color(0xFF3F1D1D),
      onErrorContainer: const Color(0xFFFCA5A5),
      outline: AppColors.darkBorder,
      outlineVariant: AppColors.darkBorder,
    );
    return _base(scheme, AppColors.darkBg, AppColors.darkDivider);
  }

  /// Component chung — chỉ khác ColorScheme + màu nền/divider theo brightness.
  static ThemeData _base(ColorScheme scheme, Color background, Color divider) {
    final bool isLight = scheme.brightness == Brightness.light;
    return ThemeData(
      useMaterial3: true,
      colorScheme: scheme,
      scaffoldBackgroundColor: background,
      // Inter nếu máy có, không có thì Flutter tự fallback — không hỏng build
      fontFamily: 'Inter',
      splashFactory: InkSparkle.splashFactory,

      // Typography: tiêu đề trang 28/700+, section 18/700, card title 15/600+,
      // body 14, caption 12, button 14/600 (weight qua các theme con).
      textTheme: Typography.blackCupertino.copyWith(
        displaySmall: TextStyle(
          fontSize: 28,
          fontWeight: FontWeight.w700,
          color: scheme.onSurface,
        ),
        titleLarge: TextStyle(
          fontSize: 18,
          fontWeight: FontWeight.w700,
          color: scheme.onSurface,
        ),
        titleMedium: TextStyle(
          fontSize: 15,
          fontWeight: FontWeight.w600,
          color: scheme.onSurface,
        ),
        bodyMedium: TextStyle(fontSize: 14, color: scheme.onSurfaceVariant),
        bodySmall: TextStyle(
          fontSize: 12,
          color: isLight ? AppColors.lightMuted : AppColors.darkMuted,
        ),
        labelLarge: TextStyle(
          fontSize: 14,
          fontWeight: FontWeight.w600,
          color: scheme.onSurface,
        ),
      ),

      appBarTheme: AppBarTheme(
        backgroundColor: background,
        foregroundColor: scheme.onSurface,
        centerTitle: false,
        elevation: 0,
        scrolledUnderElevation: 0,
        titleTextStyle: TextStyle(
          fontSize: 18,
          fontWeight: FontWeight.w700,
          color: scheme.onSurface,
        ),
      ),

      inputDecorationTheme: InputDecorationTheme(
        border: _inputBorder(scheme, scheme.outline),
        enabledBorder: _inputBorder(scheme, scheme.outline),
        focusedBorder: _inputBorder(scheme, scheme.primary, width: 1.5),
        errorBorder: _inputBorder(scheme, scheme.error),
        focusedErrorBorder: _inputBorder(scheme, scheme.error, width: 1.5),
        filled: true,
        fillColor: scheme.surface,
        hintStyle: TextStyle(
          color: isLight ? AppColors.lightMuted : AppColors.darkMuted,
        ),
        contentPadding: const EdgeInsets.symmetric(
          horizontal: 16,
          vertical: 14,
        ),
      ),

      filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(
          backgroundColor: scheme.primary,
          foregroundColor: scheme.onPrimary,
          shape: const StadiumBorder(),
          padding: const EdgeInsets.symmetric(horizontal: 22, vertical: 15),
          textStyle: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600),
        ),
      ),
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          foregroundColor: scheme.primary,
          side: BorderSide(color: scheme.outline),
          shape: const StadiumBorder(),
          padding: const EdgeInsets.symmetric(horizontal: 22, vertical: 14),
          textStyle: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600),
        ),
      ),
      textButtonTheme: TextButtonThemeData(
        style: TextButton.styleFrom(
          foregroundColor: scheme.primary,
          textStyle: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600),
        ),
      ),

      cardTheme: CardThemeData(
        elevation: 0,
        color: scheme.surface,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(18),
          side: BorderSide(color: scheme.outlineVariant),
        ),
        margin: EdgeInsets.zero,
      ),

      dividerTheme: DividerThemeData(color: divider, space: 1, thickness: 1),

      navigationRailTheme: NavigationRailThemeData(
        backgroundColor: scheme.surface,
        indicatorColor: scheme.primaryContainer,
        selectedIconTheme: IconThemeData(color: scheme.primary),
        selectedLabelTextStyle: TextStyle(
          color: scheme.primary,
          fontWeight: FontWeight.w600,
        ),
      ),
      navigationBarTheme: NavigationBarThemeData(
        backgroundColor: scheme.surface,
        indicatorColor: scheme.primaryContainer,
        height: 68,
        labelTextStyle: WidgetStatePropertyAll(
          TextStyle(
            fontSize: 12,
            fontWeight: FontWeight.w600,
            color: scheme.onSurfaceVariant,
          ),
        ),
      ),

      snackBarTheme: SnackBarThemeData(
        behavior: SnackBarBehavior.floating,
        backgroundColor: isLight
            ? AppColors.lightHeading
            : AppColors.darkHeading,
        contentTextStyle: TextStyle(
          color: isLight ? Colors.white : AppColors.darkBg,
          fontSize: 14,
        ),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
      ),

      dialogTheme: DialogThemeData(
        backgroundColor: scheme.surface,
        surfaceTintColor: Colors.transparent,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(16),
          side: BorderSide(color: scheme.outline),
        ),
        titleTextStyle: TextStyle(
          fontSize: 18,
          fontWeight: FontWeight.w700,
          color: scheme.onSurface,
        ),
      ),

      progressIndicatorTheme: ProgressIndicatorThemeData(
        color: scheme.primary,
        linearTrackColor: scheme.surfaceContainerHighest,
        circularTrackColor: scheme.surfaceContainerHighest,
      ),

      popupMenuTheme: PopupMenuThemeData(
        color: scheme.surface,
        surfaceTintColor: Colors.transparent,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(12),
          side: BorderSide(color: scheme.outline),
        ),
      ),
      tooltipTheme: TooltipThemeData(
        decoration: BoxDecoration(
          color: isLight ? AppColors.lightHeading : AppColors.darkHeading,
          borderRadius: BorderRadius.circular(8),
        ),
        textStyle: TextStyle(
          fontSize: 12,
          color: isLight ? Colors.white : AppColors.darkBg,
        ),
      ),
      checkboxTheme: CheckboxThemeData(
        fillColor: WidgetStateProperty.resolveWith(
          (Set<WidgetState> states) => states.contains(WidgetState.selected)
              ? scheme.primary
              : Colors.transparent,
        ),
        side: BorderSide(color: scheme.outline, width: 1.5),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(4)),
      ),
    );
  }

  static OutlineInputBorder _inputBorder(
    ColorScheme scheme,
    Color color, {
    double width = 1,
  }) {
    return OutlineInputBorder(
      borderRadius: BorderRadius.circular(10),
      borderSide: BorderSide(color: color, width: width),
    );
  }
}
