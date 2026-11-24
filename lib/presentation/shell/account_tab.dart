/// Tab tài khoản: thông tin phiên, credit + đăng xuất.
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../domain/entities/payment_entities.dart';
import '../payments/format_vnd.dart';
import '../payments/payment_history_screen.dart';
import '../payments/payments_providers.dart';
import '../payments/pricing_screen.dart';
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
          _sectionTitle(context, 'Plan & credits'),
          _CreditsCard(userEmail: userEmail),
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

/// Plan + credit balance, with links to the pricing screen / payment history.
class _CreditsCard extends ConsumerWidget {
  const _CreditsCard({required this.userEmail});

  final String userEmail;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final AsyncValue<CreditBalance> balance = ref.watch(creditBalanceProvider);
    final CreditBalance? b = balance.value;
    return Card(
      child: Column(
        children: <Widget>[
          if (b != null && b.expiringSoon)
            // Yellow banner: plan expires within 3 days — renew to keep it
            Container(
              width: double.infinity,
              color: Colors.amber.shade100,
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
              child: Row(
                children: <Widget>[
                  Icon(
                    Icons.warning_amber_rounded,
                    color: Colors.amber.shade900,
                    size: 18,
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      'Your plan expires in ${b.daysRemaining} day'
                      '${b.daysRemaining == 1 ? '' : 's'} — renew to keep your benefits',
                      style: TextStyle(color: Colors.amber.shade900),
                    ),
                  ),
                ],
              ),
            ),
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 4),
            child: Row(
              children: <Widget>[
                Icon(
                  b?.unlimited == true
                      ? Icons.all_inclusive
                      : Icons.toll_outlined,
                  color: Theme.of(context).colorScheme.primary,
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: <Widget>[
                      balance.when(
                        data: (CreditBalance b) {
                          final int? days = b.daysRemaining;
                          return Text(
                            days == null
                                ? 'Plan: ${b.planCode}'
                                : 'Plan: ${b.planCode} · $days day'
                                      '${days == 1 ? '' : 's'} left',
                            style: const TextStyle(
                              fontWeight: FontWeight.w800,
                              fontSize: 16,
                            ),
                          );
                        },
                        loading: () => const Text('Loading balance…'),
                        error: (Object e, StackTrace _) =>
                            const Text('Could not load the balance'),
                      ),
                      Text(
                        b == null
                            ? 'Each AI call costs credits'
                            : b.unlimited
                                  ? 'Unlimited AI usage (fair-use applies)'
                                  : 'Monthly quota ${formatCredits(b.free)}/'
                                        '${formatCredits(b.monthlyFree)} · '
                                        'Purchased ${formatCredits(b.purchased)} '
                                        '(never expires) · '
                                        'Per AI call: ${b.aiCost}',
                        style: Theme.of(context).textTheme.bodySmall,
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
          const Divider(height: 1, indent: 16, endIndent: 16),
          ListTile(
            dense: true,
            visualDensity: const VisualDensity(vertical: -4),
            contentPadding: const EdgeInsets.symmetric(horizontal: 16),
            leading: Icon(
              Icons.upgrade,
              color: Theme.of(context).colorScheme.primary,
            ),
            title: const Text('Plans'),
            subtitle: Text(
              'Upgrade or renew via bank transfer QR',
              style: Theme.of(context).textTheme.bodySmall,
            ),
            trailing: const Icon(Icons.chevron_right),
            onTap: () async {
              // Back from the pricing screen → invalidate to refresh the balance
              ref.invalidate(creditBalanceProvider);
              await Navigator.of(context).push<void>(
                MaterialPageRoute<void>(builder: (_) => const PricingScreen()),
              );
              ref.invalidate(creditBalanceProvider);
            },
          ),
          const Divider(height: 1, indent: 16, endIndent: 16),
          ListTile(
            dense: true,
            visualDensity: const VisualDensity(vertical: -4),
            contentPadding: const EdgeInsets.symmetric(horizontal: 16),
            leading: Icon(
              Icons.receipt_long_outlined,
              color: Theme.of(context).colorScheme.primary,
            ),
            title: const Text('Payment history'),
            trailing: const Icon(Icons.chevron_right),
            onTap: () => Navigator.of(context).push<void>(
              MaterialPageRoute<void>(
                builder: (_) => const PaymentHistoryScreen(),
              ),
            ),
          ),
        ],
      ),
    );
  }
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
