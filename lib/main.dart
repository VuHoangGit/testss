import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:supabase_flutter/supabase_flutter.dart';

import 'core/config/app_config.dart';
import 'core/navigation/root_navigator_key.dart';
import 'core/theme/app_theme.dart';
import 'domain/entities/user.dart';
import 'presentation/auth/auth_controller.dart';
import 'presentation/login/login_screen.dart';
import 'presentation/login/reset_password_screen.dart';
import 'presentation/providers.dart';
import 'presentation/shell/shell_screen.dart';
import 'presentation/theme/theme_mode_provider.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  // Supabase tự khôi phục phiên từ localStorage và bắt session trong URL khi
  // quay lại từ OAuth redirect (detectSessionInUrl mặc định bật).
  await Supabase.initialize(
    url: AppConfig.supabaseUrl,
    publishableKey: AppConfig.supabaseAnonKey,
  );
  runApp(const ProviderScope(child: DocuVaultApp()));
}

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
          : ShellScreen(session: session),
    );
  }
}
