/// Màn đăng nhập / đăng ký tài khoản email + mật khẩu.
///
/// Luồng Google giữ nguyên code chờ cấu hình OAuth client ID (xem README).
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

  Future<void> _submit() async {
    if (!(_formKey.currentState?.validate() ?? false)) return;
    final AuthController controller = ref.read(authControllerProvider.notifier);
    final String email = _email.text.trim();
    final String password = _password.text;
    try {
      if (_registerMode) {
        await controller.signUp(email: email, password: password, name: _name.text.trim());
        // Đăng ký xong KHÔNG tự đăng nhập — quay lại form đăng nhập, giữ sẵn email
        setState(() {
          _registerMode = false;
          _password.clear();
        });
        _showSnack('Đăng ký thành công. Hãy đăng nhập.');
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
                        ? 'Tạo tài khoản mới'
                        : 'Kho tài liệu thông minh của bạn',
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
                      labelText: 'Email',
                      prefixIcon: Icon(Icons.alternate_email),
                    ),
                    validator: (String? v) {
                      final String value = v?.trim() ?? '';
                      if (value.isEmpty) return 'Nhập email';
                      if (!value.contains('@')) return 'Email không hợp lệ';
                      return null;
                    },
                  ),
                  const SizedBox(height: 12),
                  if (_registerMode) ...<Widget>[
                    TextFormField(
                      controller: _name,
                      decoration: const InputDecoration(
                        labelText: 'Tên hiển thị (tùy chọn)',
                        prefixIcon: Icon(Icons.person_outline),
                      ),
                    ),
                    const SizedBox(height: 12),
                  ],
                  TextFormField(
                    controller: _password,
                    obscureText: true,
                    decoration: InputDecoration(
                      labelText: 'Mật khẩu',
                      helperText: _registerMode ? 'Tối thiểu 6 ký tự' : null,
                      prefixIcon: const Icon(Icons.lock_outline),
                    ),
                    validator: (String? v) {
                      final String value = v ?? '';
                      if (value.isEmpty) return 'Nhập mật khẩu';
                      if (_registerMode && value.length < 6) {
                        return 'Mật khẩu tối thiểu 6 ký tự';
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
                    label: Text(_registerMode ? 'Đăng ký' : 'Đăng nhập'),
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
                          ? 'Đã có tài khoản? Đăng nhập'
                          : 'Chưa có tài khoản? Đăng ký',
                    ),
                  ),
                  const SizedBox(height: 8),
                  OutlinedButton.icon(
                    onPressed: busy
                        ? null
                        : () => _showSnack(
                              'Đăng nhập Google sẽ được bật sau khi cấu hình '
                              'OAuth client ID (xem README).',
                            ),
                    icon: const Icon(Icons.g_mobiledata),
                    label: const Text('Đăng nhập bằng Google'),
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
