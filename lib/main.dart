import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:supabase_flutter/supabase_flutter.dart';

import 'core/config/app_config.dart';
import 'core/navigation/root_navigator_key.dart';
import 'core/theme/app_theme.dart';
import 'domain/entities/user.dart';
import 'presentation/auth/auth_controller.dart';
import 'presentation/auth/name_setup_screen.dart';
import 'presentation/login/login_screen.dart';
import 'presentation/login/reset_password_screen.dart';
import 'presentation/providers.dart';
import 'presentation/shared/shared_view_screen.dart';
import 'presentation/shell/shell_screen.dart';
import 'presentation/theme/theme_mode_provider.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  // Đọc token trước khi Supabase xử lý URL OAuth để không mất deep link chia sẻ.
  if (kIsWeb) {
    final String? shareToken = Uri.base.queryParameters['share'];
    if (shareToken != null && shareToken.isNotEmpty) {
      initialShareToken = shareToken;
    }
  }
  // Supabase tự khôi phục phiên và bắt session trong URL OAuth redirect.
  await Supabase.initialize(
    url: AppConfig.supabaseUrl,
    publishableKey: AppConfig.supabaseAnonKey,
  );
  runApp(const ProviderScope(child: DocuVaultApp()));
}

/// Token chia sẻ từ URL lúc khởi động (?share=…) — null khi mở app bình thường.
String? initialShareToken;

class DocuVaultApp extends ConsumerWidget {
  const DocuVaultApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return MaterialApp(
      title: 'DocuVault',
      debugShowCheckedModeBanner: false,
      theme: AppTheme.light(),
      darkTheme: AppTheme.dark(),
      themeMode: ref.watch(themeModeProvider),
      navigatorKey: rootNavigatorKey,
      home: const AuthGate(),
    );
  }
}

/// Routes to Login or Shell based on authentication state.
class AuthGate extends ConsumerWidget {
  const AuthGate({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final AsyncValue<AuthSession?> auth = ref.watch(authControllerProvider);
    // Phiên đến từ link "Quên mật khẩu" → màn đặt mật khẩu mới thay vì app
    final bool recovery = ref.watch(passwordRecoveryProvider);
    // Link chia sẻ ưu tiên trước mọi màn: người nhận xem thẳng SharedView,
    // bỏ qua login kể cả khi app đang lưu phiên tài khoản khác (FR-3.1).
    final String? shareToken = initialShareToken;
    if (shareToken != null) {
      return SharedViewScreen(token: shareToken);
    }

    return auth.when(
      loading: () =>
          const Scaffold(body: Center(child: CircularProgressIndicator())),
      error: (Object e, StackTrace _) => Scaffold(
        body: Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              Text('Unable to start session: $e'),
              const SizedBox(height: 12),
              FilledButton(
                onPressed: () => ref.invalidate(authControllerProvider),
                child: const Text('Try again'),
              ),
            ],
          ),
        ),
      ),
      data: (AuthSession? session) => session == null
          ? const LoginScreen()
          : recovery
          ? const ResetPasswordScreen()
          // Lần đăng nhập đầu tiên (chưa tự đặt tên) → hỏi tên rồi mới vào app
          : !session.user.nameChosen
          ? NameSetupScreen(session: session)
          : ShellScreen(session: session),
    );
  }
}
