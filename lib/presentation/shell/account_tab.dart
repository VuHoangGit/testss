/// Tab tài khoản: thông tin phiên + đăng xuất.
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../providers.dart';

class AccountTab extends ConsumerWidget {
  const AccountTab({super.key, required this.userEmail});

  final String userEmail;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return ListView(
      padding: const EdgeInsets.all(16),
      children: <Widget>[
        Card(
          child: ListTile(
            leading: const Icon(Icons.account_circle, size: 40),
            title: Text(userEmail),
            subtitle: const Text('Đăng nhập phiên hiện tại'),
          ),
        ),
        const SizedBox(height: 12),
        Card(
          child: ListTile(
            leading: Icon(Icons.logout, color: Theme.of(context).colorScheme.error),
            title: const Text('Đăng xuất'),
            onTap: () async {
              final bool? ok = await showDialog<bool>(
                context: context,
                builder: (BuildContext ctx) => AlertDialog(
                  title: const Text('Đăng xuất?'),
                  content: const Text('Phiên trên thiết bị này sẽ kết thúc. Dữ liệu không bị xóa.'),
                  actions: <Widget>[
                    TextButton(
                      onPressed: () => Navigator.pop(ctx, false),
                      child: const Text('Hủy'),
                    ),
                    FilledButton(
                      onPressed: () => Navigator.pop(ctx, true),
                      child: const Text('Đăng xuất'),
                    ),
                  ],
                ),
              );
              if (ok ?? false) {
                await ref.read(authControllerProvider.notifier).signOut();
              }
            },
          ),
        ),
      ],
    );
  }
}
