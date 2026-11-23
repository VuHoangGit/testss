/// Màn đặt tên hiển thị ngay sau lần đăng nhập đầu tiên.
///
/// AuthGate hiện màn này khi `session.user.nameChosen == false` (backend trả
/// `name_chosen_at = null`). Người dùng nhập tên → lưu qua PATCH /auth/me →
/// state đổi thành phiên đã có tên → vào thẳng app chính. Google/email đều đi
/// qua cùng một bước này.
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../domain/entities/user.dart';
import '../providers.dart';

class NameSetupScreen extends ConsumerStatefulWidget {
  const NameSetupScreen({super.key, required this.session});

  /// Phiên vừa đăng nhập — dùng để điền sẵn tên Google (nếu có).
  final AuthSession session;

  @override
  ConsumerState<NameSetupScreen> createState() => _NameSetupScreenState();
}

class _NameSetupScreenState extends ConsumerState<NameSetupScreen> {
  late final TextEditingController _name = TextEditingController(
    // Tên Google có sẵn chỉ là gợi ý: người dùng sửa được, hoặc bấm Continue
    // để dùng luôn.
    text: widget.session.user.name ?? '',
  );
  final GlobalKey<FormState> _formKey = GlobalKey<FormState>();
  bool _busy = false;

  @override
  void dispose() {
    _name.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (_busy || !(_formKey.currentState?.validate() ?? false)) return;
    setState(() => _busy = true);
    try {
      await ref
          .read(authControllerProvider.notifier)
          .setDisplayName(_name.text.trim());
      // Thành công: AuthGate tự chuyển sang ShellScreen, không cần Navigator.
    } on Exception catch (e) {
      if (!mounted) return;
      setState(() => _busy = false);
      ScaffoldMessenger.of(context)
        ..hideCurrentSnackBar()
        ..showSnackBar(
          SnackBar(
            content: Text('$e'),
            backgroundColor: Theme.of(context).colorScheme.error,
          ),
        );
    }
  }

  /// Thoát khỏi màn đặt tên (đăng xuất để dùng tài khoản khác) — tránh kẹt.
  Future<void> _signOut() async {
    await ref.read(authControllerProvider.notifier).signOut();
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return Scaffold(
      body: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 420),
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(24),
            child: Form(
              key: _formKey,
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: <Widget>[
                  Icon(
                    Icons.waving_hand_rounded,
                    size: 56,
                    color: theme.colorScheme.primary,
                  ),
                  const SizedBox(height: 12),
                  Text(
                    'What should we call you?',
                    textAlign: TextAlign.center,
                    style: theme.textTheme.headlineMedium?.copyWith(
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                  const SizedBox(height: 6),
                  Text(
                    'Signed in as ${widget.session.user.email}. Pick the name '
                    'you want to see in your workspace.',
                    textAlign: TextAlign.center,
                    style: theme.textTheme.bodyMedium?.copyWith(
                      color: theme.colorScheme.onSurfaceVariant,
                    ),
                  ),
                  const SizedBox(height: 24),
                  TextFormField(
                    controller: _name,
                    autofocus: true,
                    textInputAction: TextInputAction.done,
                    textCapitalization: TextCapitalization.words,
                    decoration: const InputDecoration(
                      labelText: 'Display name',
                      helperText: 'For example: Hoàng Vũ',
                      prefixIcon: Icon(Icons.person_outline),
                    ),
                    validator: (String? v) {
                      final String value = (v ?? '').trim();
                      if (value.isEmpty) return 'Enter your name';
                      if (value.length > 255) {
                        return 'Name is too long (255 characters max)';
                      }
                      return null;
                    },
                    onFieldSubmitted: (String _) => _busy ? null : _submit(),
                  ),
                  const SizedBox(height: 20),
                  FilledButton.icon(
                    onPressed: _busy ? null : _submit,
                    style: FilledButton.styleFrom(
                      minimumSize: const Size.fromHeight(48),
                    ),
                    icon: _busy
                        ? const SizedBox(
                            width: 18,
                            height: 18,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        : const Icon(Icons.arrow_forward_rounded),
                    label: const Text('Continue'),
                  ),
                  const SizedBox(height: 4),
                  TextButton(
                    onPressed: _busy ? null : _signOut,
                    child: const Text('Use another account'),
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
