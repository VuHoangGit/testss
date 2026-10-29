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

  /// Mở dialog nhập email → gửi link đặt lại mật khẩu (Supabase gửi email).
  Future<void> _forgotPassword() async {
    // Không dùng TextEditingController: dialog đóng (animation chạy) trong khi
    // controller đã dispose sẽ ném assertion — giữ giá trị qua onChanged.
    String email = _email.text.trim();
    final String? result = await showDialog<String>(
      context: context,
      builder: (BuildContext dialogContext) => AlertDialog(
        title: const Text('Reset password'),
        content: TextField(
          keyboardType: TextInputType.emailAddress,
          autofocus: true,
          onChanged: (String value) => email = value.trim(),
          decoration: InputDecoration(
            labelText: 'Email address',
            prefixIcon: const Icon(Icons.alternate_email),
            errorText: email.isNotEmpty && !email.contains('@')
                ? 'Enter a valid email'
                : null,
          ),
        ),
        actions: <Widget>[
          TextButton(
            onPressed: () => Navigator.of(dialogContext).pop(),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.of(dialogContext).pop(email),
            child: const Text('Send email'),
          ),
        ],
      ),
    );
    if (result == null || result.isEmpty || !result.contains('@')) return;
    try {
      await ref.read(authControllerProvider.notifier).sendPasswordReset(result);
      _showSnack('Reset email sent — check your inbox.');
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
    final bool wide = MediaQuery.sizeOf(context).width >= 900;

    if (wide) {
      // Desktop: brand panel trái + form phải (spec login 2 cột)
      return Scaffold(
        body: Row(
          children: <Widget>[
            const Expanded(flex: 5, child: _BrandPanel()),
            Expanded(
              flex: 6,
              child: Center(
                child: SingleChildScrollView(
                  padding: const EdgeInsets.all(32),
                  child: ConstrainedBox(
                    constraints: const BoxConstraints(maxWidth: 420),
                    child: _buildForm(context, busy, showLogo: false),
                  ),
                ),
              ),
            ),
          ],
        ),
      );
    }

    // Mobile/tablet: 1 cột, logo phía trên form.
    // Padding/spacing thu gọn để form vừa viewport nhỏ (không cần cuộn).
    return Scaffold(
      body: Center(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(16),
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 420),
            child: _buildForm(context, busy, showLogo: true, compact: true),
          ),
        ),
      ),
    );
  }

  /// Form đăng nhập/đăng ký dùng chung cho mọi kích thước màn hình.
  /// [compact] thu nhỏ khoảng cách cho màn hình thấp (mobile).
  Widget _buildForm(
    BuildContext context,
    bool busy, {
    required bool showLogo,
    bool compact = false,
  }) {
    // Compact: khoảng cách gọn để mọi nút hiện trong viewport 600px
    final double s = compact ? 10 : 16;
    final double sectionGap = compact ? 14 : 20;
    return Form(
      key: _formKey,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          if (showLogo) ...<Widget>[
            Icon(
              Icons.folder_special_rounded,
              size: compact ? 40 : 56,
              color: Theme.of(context).colorScheme.primary,
            ),
            SizedBox(height: compact ? 8 : 12),
            Text(
              'DocuVault',
              textAlign: TextAlign.center,
              style: Theme.of(context).textTheme.headlineMedium
                  ?.copyWith(fontWeight: FontWeight.bold),
            ),
            SizedBox(height: compact ? 16 : 24),
          ],
          Text(
            _registerMode ? 'Create your account' : 'Welcome back',
            style: Theme.of(context).textTheme.displaySmall,
          ),
          const SizedBox(height: 6),
          Text(
            _registerMode
                ? 'Start your intelligent document workspace'
                : 'Sign in to your workspace',
            style: Theme.of(context).textTheme.bodyMedium?.copyWith(
              color: Theme.of(context).colorScheme.onSurfaceVariant,
            ),
          ),
          SizedBox(height: sectionGap),
          OutlinedButton.icon(
            onPressed: busy ? null : _signInWithGoogle,
            icon: const Icon(Icons.g_mobiledata),
            style: OutlinedButton.styleFrom(
              backgroundColor: Theme.of(context).colorScheme.surface,
            ),
            label: const Text('Continue with Google'),
          ),
          SizedBox(height: s),
          Row(
            children: <Widget>[
              const Expanded(child: Divider()),
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 12),
                child: Text(
                  'or continue with email',
                  style: Theme.of(context).textTheme.bodySmall,
                ),
              ),
              const Expanded(child: Divider()),
            ],
          ),
          SizedBox(height: s),
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
          SizedBox(height: s),
          if (_registerMode) ...<Widget>[
            TextFormField(
              controller: _name,
              decoration: const InputDecoration(
                labelText: 'Display name (optional)',
                prefixIcon: Icon(Icons.person_outline),
              ),
            ),
            SizedBox(height: s),
          ],
          TextFormField(
            controller: _password,
            obscureText: true,
            decoration: InputDecoration(
              labelText: 'Password',
              helperText: _registerMode ? 'At least 6 characters' : null,
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
          SizedBox(height: compact ? 14 : 20),
          FilledButton.icon(
            onPressed: busy ? null : _submit,
            style: FilledButton.styleFrom(
              minimumSize: const Size.fromHeight(48),
            ),
            icon: busy
                ? const SizedBox(
                    width: 18,
                    height: 18,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : Icon(_registerMode ? Icons.person_add : Icons.login),
            label: Text(_registerMode ? 'Create account' : 'Sign in'),
          ),
          if (!_registerMode) ...<Widget>[
            const SizedBox(height: 2),
            Align(
              alignment: Alignment.centerRight,
              child: TextButton(
                onPressed: busy ? null : _forgotPassword,
                child: const Text('Forgot password?'),
              ),
            ),
          ],
          const SizedBox(height: 2),
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
        ],
      ),
    );
  }
}

/// Panel branding trái (desktop): gradient indigo → violet + thông điệp chính.
class _BrandPanel extends StatelessWidget {
  const _BrandPanel();

  static const List<(IconData, String, String)> _points =
      <(IconData, String, String)>[
        (
          Icons.auto_awesome_outlined,
          'Chat with your PDFs',
          'Ask questions and get answers grounded in your documents',
        ),
        (
          Icons.document_scanner_outlined,
          'OCR & translate in seconds',
          'Extract text from scans, translate to 20+ languages',
        ),
        (
          Icons.lock_outline,
          'Secure private vault',
          'Your files stay encrypted and accessible only to you',
        ),
      ];

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: const BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: <Color>[
            Color(0xFF312E81),
            Color(0xFF4F46E5),
            Color(0xFF7C3AED),
          ],
        ),
      ),
      child: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(48),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Row(
                children: <Widget>[
                  Container(
                    width: 36,
                    height: 36,
                    decoration: BoxDecoration(
                      color: Colors.white.withValues(alpha: 0.18),
                      borderRadius: BorderRadius.circular(11),
                    ),
                    child: const Icon(
                      Icons.folder_special_rounded,
                      color: Colors.white,
                      size: 21,
                    ),
                  ),
                  const SizedBox(width: 10),
                  Text(
                    'DocuVault',
                    style: Theme.of(context).textTheme.titleLarge?.copyWith(
                      color: Colors.white,
                      fontWeight: FontWeight.w800,
                    ),
                  ),
                ],
              ),
              const Spacer(),
              Text(
                'Your documents,\nbut smarter.',
                style: Theme.of(context).textTheme.displayLarge?.copyWith(
                  color: Colors.white,
                  fontWeight: FontWeight.w800,
                  height: 1.15,
                ),
              ),
              const SizedBox(height: 12),
              Text(
                'An AI-native workspace that helps you store, search and understand every file.',
                style: Theme.of(context).textTheme.bodyLarge?.copyWith(
                  color: Colors.white.withValues(alpha: 0.85),
                  height: 1.5,
                ),
              ),
              const SizedBox(height: 40),
              for (final (IconData, String, String) p in _points) ...<Widget>[
                Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: <Widget>[
                    Container(
                      width: 36,
                      height: 36,
                      decoration: BoxDecoration(
                        color: Colors.white.withValues(alpha: 0.14),
                        borderRadius: BorderRadius.circular(10),
                      ),
                      child: Icon(p.$1, color: Colors.white, size: 19),
                    ),
                    const SizedBox(width: 14),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: <Widget>[
                          Text(
                            p.$2,
                            style: const TextStyle(
                              color: Colors.white,
                              fontSize: 15,
                              fontWeight: FontWeight.w600,
                            ),
                          ),
                          const SizedBox(height: 2),
                          Text(
                            p.$3,
                            style: TextStyle(
                              color: Colors.white.withValues(alpha: 0.75),
                              fontSize: 13,
                              height: 1.45,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 20),
              ],
              const Spacer(),
            ],
          ),
        ),
      ),
    );
  }
}
