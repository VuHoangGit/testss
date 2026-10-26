/// Đăng nhập email/mật khẩu + Google (Supabase Auth).
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../auth/auth_controller.dart';
import '../providers.dart';

class LoginScreen extends ConsumerStatefulWidget {
  const LoginScreen({super.key});

  @override
  ConsumerState<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends ConsumerState<LoginScreen> {
  final TextEditingController _email = TextEditingController();
  final TextEditingController _password = TextEditingController();
  final TextEditingController _name = TextEditingController();
  final GlobalKey<FormState> _formKey = GlobalKey<FormState>();
  bool _registerMode = false;

  @override
  void dispose() {
    _email.dispose();
    _password.dispose();
    _name.dispose();
    super.dispose();
  }

  void _showSnack(String message, {bool isError = false}) {
    if (!mounted) return;
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(
        SnackBar(
          content: Text(message),
          backgroundColor: isError ? Theme.of(context).colorScheme.error : null,
        ),
      );
  }

  /// Đăng nhập Google qua Supabase: mở cửa sổ Google; khi thành công phiên
  /// về qua sessionChanged và AuthGate tự chuyển màn — ở đây chỉ bắt lỗi.
  Future<void> _signInWithGoogle() async {
    try {
      await ref.read(authControllerProvider.notifier).signInWithGoogle();
    } on Exception catch (e) {
      _showSnack('$e', isError: true);
    }
  }

  Future<void> _submit() async {
    if (!(_formKey.currentState?.validate() ?? false)) return;
    final AuthController controller = ref.read(authControllerProvider.notifier);
    final String email = _email.text.trim();
    final String password = _password.text;
    try {
      if (_registerMode) {
        await controller.signUp(
          email: email,
          password: password,
          name: _name.text.trim(),
        );
        // Đăng ký xong KHÔNG tự đăng nhập — quay lại form đăng nhập, giữ sẵn email
        setState(() {
          _registerMode = false;
          _password.clear();
        });
        _showSnack('Account created successfully. Please sign in.');
      } else {
        await controller.signIn(email: email, password: password);
      }
    } on Exception catch (e) {
      _showSnack('$e', isError: true);
    }
  }

  @override
  Widget build(BuildContext context) {
    final AsyncValue<void> state = ref.watch(authControllerProvider);
    final bool busy = state.isLoading;

    return Scaffold(
      body: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 400),
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(24),
            child: Form(
              key: _formKey,
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: <Widget>[
                  Icon(
                    Icons.folder_special_rounded,
                    size: 64,
                    color: Theme.of(context).colorScheme.primary,
                  ),
                  const SizedBox(height: 12),
                  Text(
                    'DocuVault',
                    textAlign: TextAlign.center,
                    style: Theme.of(context).textTheme.headlineMedium
                        ?.copyWith(fontWeight: FontWeight.bold),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    _registerMode
                        ? 'Create your account'
                        : 'Your intelligent document workspace',
                    textAlign: TextAlign.center,
                    style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                      color: Theme.of(context).colorScheme.outline,
                    ),
                  ),
                  const SizedBox(height: 28),
                  TextFormField(
                    controller: _email,
                    keyboardType: TextInputType.emailAddress,
                    decoration: const InputDecoration(
                      labelText: 'Email address',
                      prefixIcon: Icon(Icons.alternate_email),
                    ),
                    validator: (String? v) {
                      final String value = v?.trim() ?? '';
                      if (value.isEmpty) return 'Enter your email';
                      if (!value.contains('@')) return 'Enter a valid email';
                      return null;
                    },
                  ),
                  const SizedBox(height: 12),
                  if (_registerMode) ...<Widget>[
                    TextFormField(
                      controller: _name,
                      decoration: const InputDecoration(
                        labelText: 'Display name (optional)',
                        prefixIcon: Icon(Icons.person_outline),
                      ),
                    ),
                    const SizedBox(height: 12),
                  ],
                  TextFormField(
                    controller: _password,
                    obscureText: true,
                    decoration: InputDecoration(
                      labelText: 'Password',
                      helperText: _registerMode
                          ? 'At least 6 characters'
                          : null,
                      prefixIcon: const Icon(Icons.lock_outline),
                    ),
                    validator: (String? v) {
                      final String value = v ?? '';
                      if (value.isEmpty) return 'Enter your password';
                      if (_registerMode && value.length < 6) {
                        return 'Password must be at least 6 characters';
                      }
                      return null;
                    },
                    onFieldSubmitted: (String _) => busy ? null : _submit(),
                  ),
                  const SizedBox(height: 20),
                  FilledButton.icon(
                    onPressed: busy ? null : _submit,
                    icon: busy
                        ? const SizedBox(
                            width: 18,
                            height: 18,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        : Icon(_registerMode ? Icons.person_add : Icons.login),
                    label: Text(_registerMode ? 'Create account' : 'Sign in'),
                  ),
                  const SizedBox(height: 4),
                  TextButton(
                    onPressed: busy
                        ? null
                        : () => setState(() {
                            _registerMode = !_registerMode;
                            _password.clear();
                          }),
                    child: Text(
                      _registerMode
                          ? 'Already have an account? Sign in'
                          : 'New to DocuVault? Create an account',
                    ),
                  ),
                  const SizedBox(height: 8),
                  OutlinedButton.icon(
                    onPressed: busy ? null : _signInWithGoogle,
                    icon: const Icon(Icons.g_mobiledata),
                    label: const Text('Continue with Google'),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
