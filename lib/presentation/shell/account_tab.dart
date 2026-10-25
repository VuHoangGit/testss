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
            subtitle: const Text('Signed in to your workspace'),
          ),
        ),
        const SizedBox(height: 12),
        Card(
          child: ListTile(
            leading: Icon(
              Icons.logout,
              color: Theme.of(context).colorScheme.error,
            ),
            title: const Text('Sign out'),
            onTap: () async {
              final bool? ok = await showDialog<bool>(
                context: context,
                builder: (BuildContext ctx) => AlertDialog(
                  title: const Text('Sign out?'),
                  content: const Text(
                    'Your session will end on this device. Your data will not be deleted.',
                  ),
                  actions: <Widget>[
                    TextButton(
                      onPressed: () => Navigator.pop(ctx, false),
                      child: const Text('Cancel'),
                    ),
                    FilledButton(
                      onPressed: () => Navigator.pop(ctx, true),
                      child: const Text('Sign out'),
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
