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
    // SingleChildScrollView + Column (không lazy như ListView): trong
    // IndexedStack viewport thấp, mọi section vẫn được build sẵn.
    return SingleChildScrollView(
      padding: const EdgeInsets.fromLTRB(28, 16, 28, 16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          Text(
            'Account settings',
            style: Theme.of(context).textTheme.titleLarge,
          ),
          const SizedBox(height: 4),
          Text(
            'Manage your profile, preferences and workspace.',
            style: Theme.of(context).textTheme.bodySmall,
          ),
          const SizedBox(height: 14),
          // Security lên đầu: hành động quan trọng + luôn trong viewport
          // (không bị NavigationBar che trên màn thấp).
          _sectionTitle(context, 'Security'),
          const _SignOutTile(),
          const SizedBox(height: 14),
          _sectionTitle(context, 'Profile'),
          Card(
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
              child: Row(
                children: <Widget>[
                  CircleAvatar(
                    radius: 20,
                    backgroundColor: Theme.of(context)
                        .colorScheme
                        .primaryContainer,
                    child: Text(
                      userEmail.isEmpty ? '?' : userEmail[0].toUpperCase(),
                      style: TextStyle(
                        fontSize: 15,
                        color: Theme.of(context).colorScheme.primary,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: <Widget>[
                        const Text(
                          'Workspace member',
                          style: TextStyle(fontWeight: FontWeight.w700),
                        ),
                        Text(
                          userEmail,
                          style: Theme.of(context).textTheme.bodySmall,
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 14),
          _sectionTitle(context, 'Preferences'),
          Card(
            child: Column(
              children: <Widget>[
                ListTile(
                  dense: true,
                  visualDensity: const VisualDensity(vertical: -4),
                  contentPadding: const EdgeInsets.symmetric(horizontal: 16),
                  leading: Icon(
                    Icons.palette_outlined,
                    color: Theme.of(context).colorScheme.primary,
                  ),
                  title: const Text('Appearance'),
                  subtitle: Text(
                    'Use the theme toggle in the top bar to switch light/dark',
                    style: Theme.of(context).textTheme.bodySmall,
                  ),
                ),
                const Divider(height: 1, indent: 16, endIndent: 16),
                ListTile(
                  dense: true,
                  visualDensity: const VisualDensity(vertical: -4),
                  contentPadding: const EdgeInsets.symmetric(horizontal: 16),
                  leading: Icon(
                    Icons.mic_none,
                    color: Theme.of(context).colorScheme.primary,
                  ),
                  title: const Text('Voice assistant'),
                  subtitle: Text(
                    'Tap the mic in the top bar to control the workspace by voice',
                    style: Theme.of(context).textTheme.bodySmall,
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 14),
          _sectionTitle(context, 'Storage'),
          Card(
            child: ListTile(
              dense: true,
              visualDensity: const VisualDensity(vertical: -4),
              contentPadding: const EdgeInsets.symmetric(horizontal: 16),
              leading: Icon(
                Icons.cloud_outlined,
                color: Theme.of(context).colorScheme.primary,
              ),
              title: const Text('Storage usage'),
              subtitle: Text(
                'Coming soon',
                style: Theme.of(context).textTheme.bodySmall,
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _sectionTitle(BuildContext context, String label) => Padding(
    padding: const EdgeInsets.only(left: 4, bottom: 6),
    child: Text(
      label.toUpperCase(),
      style: Theme.of(context).textTheme.labelSmall?.copyWith(
        letterSpacing: 1.1,
        fontWeight: FontWeight.w700,
        color: Theme.of(context).colorScheme.outline,
      ),
    ),
  );
}

class _SignOutTile extends ConsumerWidget {
  const _SignOutTile();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Card(
      child: ListTile(
        dense: true,
        contentPadding: const EdgeInsets.symmetric(horizontal: 16),
        leading: Icon(Icons.logout, color: Theme.of(context).colorScheme.error),
        title: Text(
          'Sign out',
          style: TextStyle(color: Theme.of(context).colorScheme.error),
        ),
        subtitle: const Text('End your session on this device'),
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
    );
  }
}
