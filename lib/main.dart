import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'core/navigation/root_navigator_key.dart';
import 'core/theme/app_theme.dart';
import 'domain/entities/user.dart';
import 'presentation/login/login_screen.dart';
import 'presentation/providers.dart';
import 'presentation/shell/shell_screen.dart';

Future<void> main() async {
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
      navigatorKey: rootNavigatorKey,
      home: const AuthGate(),
    );
  }
}

/// Điều hướng theo trạng thái xác thực: splash → Login hoặc Shell.
class AuthGate extends ConsumerWidget {
  const AuthGate({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final AsyncValue<AuthSession?> auth = ref.watch(authControllerProvider);

    return auth.when(
      loading: () => const Scaffold(body: Center(child: CircularProgressIndicator())),
      error: (Object e, StackTrace _) => Scaffold(
        body: Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              Text('Không khởi động được phiên: $e'),
              const SizedBox(height: 12),
              FilledButton(
                onPressed: () => ref.invalidate(authControllerProvider),
                child: const Text('Thử lại'),
              ),
            ],
          ),
        ),
      ),
      data: (AuthSession? session) =>
          session == null ? const LoginScreen() : ShellScreen(session: session),
    );
  }
}
