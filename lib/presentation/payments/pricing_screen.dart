/// Pricing screen: current plan banner + a comparison column of 4 plan cards.
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../domain/entities/payment_entities.dart';
import 'format_vnd.dart';
import 'order_screen.dart';
import 'payments_providers.dart';

class PricingScreen extends ConsumerWidget {
  const PricingScreen({super.key});

  Future<void> _buyPlan(
    BuildContext context,
    WidgetRef ref,
    String code,
  ) async {
    try {
      final PaymentOrder order = await ref
          .read(paymentsRepositoryProvider)
          .createOrder(code);
      if (!context.mounted) return;
      await Navigator.of(context).push<void>(
        MaterialPageRoute<void>(builder: (_) => OrderScreen(order: order)),
      );
      // Back from the payment screen (paid or closed) → refresh the balance
      ref.invalidate(creditBalanceProvider);
      ref.invalidate(pricingPackagesProvider);
    } on Exception catch (e) {
      if (!context.mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('$e'),
          backgroundColor: Theme.of(context).colorScheme.error,
        ),
      );
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final AsyncValue<CreditBalance> balance = ref.watch(creditBalanceProvider);
    final AsyncValue<List<PricingPackage>> packages = ref.watch(
      pricingPackagesProvider,
    );

    // Yellow renewal banner when the current plan expires within 3 days
    final CreditBalance? b = balance.value;
    if (b != null && b.expiringSoon) {
      return Scaffold(
        appBar: AppBar(title: const Text('Plans')),
        body: Column(
          children: <Widget>[
            _ExpiringBanner(daysLeft: b.daysRemaining ?? 0),
            Expanded(child: _buildBody(context, ref, balance, packages)),
          ],
        ),
      );
    }
    return Scaffold(
      appBar: AppBar(title: const Text('Plans')),
      body: _buildBody(context, ref, balance, packages),
    );
  }

  Widget _buildBody(
    BuildContext context,
    WidgetRef ref,
    AsyncValue<CreditBalance> balance,
    AsyncValue<List<PricingPackage>> packages,
  ) {
    return ListView(
      padding: const EdgeInsets.fromLTRB(20, 12, 20, 24),
      children: <Widget>[
        Card(
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: balance.when(
              data: (CreditBalance b) => _CurrentPlanSummary(balance: b),
              loading: () => const Center(
                child: Padding(
                  padding: EdgeInsets.all(8),
                  child: CircularProgressIndicator(strokeWidth: 2),
                ),
              ),
              error: (Object e, StackTrace _) => Padding(
                padding: const EdgeInsets.all(8),
                child: Text('Could not load the balance: $e'),
              ),
            ),
          ),
        ),
        const SizedBox(height: 12),
        Text(
          'CHOOSE A MONTHLY PLAN',
          style: Theme.of(context).textTheme.labelSmall?.copyWith(
            letterSpacing: 1.1,
            fontWeight: FontWeight.w700,
            color: Theme.of(context).colorScheme.outline,
          ),
        ),
        const SizedBox(height: 8),
        packages.when(
          data: (List<PricingPackage> list) => Column(
            children: <Widget>[
              for (final PricingPackage p in list)
                Padding(
                  padding: const EdgeInsets.only(bottom: 12),
                  child: _PlanCard(
                    pkg: p,
                    currentPlan: balance.value?.planCode ?? 'FREE',
                    // Cost per AI call comes from the balance; fallback 50
                    // (the backend default) while the balance is loading.
                    aiCost: balance.value?.aiCost ?? 50,
                    onTap: () => _buyPlan(context, ref, p.code),
                  ),
                ),
            ],
          ),
          loading: () => const Center(child: CircularProgressIndicator()),
          error: (Object e, StackTrace _) => Padding(
            padding: const EdgeInsets.all(16),
            child: Text('$e', style: const TextStyle(color: Colors.red)),
          ),
        ),
        const SizedBox(height: 4),
        Text(
          'Monthly quotas reset each cycle and never roll over. Legacy '
          'purchased credits are kept and spent after the monthly quota.',
          style: Theme.of(context).textTheme.bodySmall?.copyWith(
            color: Theme.of(context).colorScheme.onSurfaceVariant,
          ),
        ),
      ],
    );
  }
}

/// "Plan: Plus · 18 days left" + quota usage summary.
class _CurrentPlanSummary extends StatelessWidget {
  const _CurrentPlanSummary({required this.balance});

  final CreditBalance balance;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final int? days = balance.daysRemaining;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        Row(
          children: <Widget>[
            Icon(
              balance.unlimited ? Icons.all_inclusive : Icons.toll_outlined,
              color: theme.colorScheme.primary,
            ),
            const SizedBox(width: 10),
            Expanded(
              child: Text(
                days == null
                    ? 'Plan: ${balance.planCode}'
                    : 'Plan: ${balance.planCode} · $days day'
                          '${days == 1 ? '' : 's'} left',
                style: theme.textTheme.titleMedium?.copyWith(
                  fontWeight: FontWeight.w800,
                ),
              ),
            ),
          ],
        ),
        const SizedBox(height: 6),
        Text(
          balance.unlimited
              ? 'Unlimited AI usage (fair-use applies) · '
                '${formatCredits(balance.purchased)} purchased credits in reserve'
              : 'Monthly quota: ${formatCredits(balance.free)}/'
                  '${formatCredits(balance.monthlyFree)} credits · '
                  'Purchased: ${formatCredits(balance.purchased)} · '
                  'Per AI call: ${balance.aiCost}',
          style: theme.textTheme.bodySmall,
        ),
      ],
    );
  }
}

/// Yellow banner urging renewal when the plan expires within 3 days.
class _ExpiringBanner extends StatelessWidget {
  const _ExpiringBanner({required this.daysLeft});

  final int daysLeft;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: Colors.amber.shade100,
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 10),
        child: Row(
          children: <Widget>[
            Icon(Icons.warning_amber_rounded, color: Colors.amber.shade900),
            const SizedBox(width: 10),
            Expanded(
              child: Text(
                'Your plan expires in $daysLeft day'
                '${daysLeft == 1 ? '' : 's'} — renew now to keep your benefits.',
                style: TextStyle(color: Colors.amber.shade900),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _PlanCard extends StatelessWidget {
  const _PlanCard({
    required this.pkg,
    required this.currentPlan,
    required this.aiCost,
    required this.onTap,
  });

  final PricingPackage pkg;

  /// Effective plan code of the signed-in user ("PLUS"...).
  final String currentPlan;

  /// Cost per AI call (backend settings.credit_cost_ai) — for "~X AI calls".
  final int aiCost;

  final VoidCallback onTap;

  String get _headline =>
      pkg.unlimited ? 'Unlimited' : '${pkg.credits ~/ aiCost} AI calls / month';

  @override
  Widget build(BuildContext context) {
    final ColorScheme colors = Theme.of(context).colorScheme;
    final bool featured = pkg.isFeatured;
    final bool isCurrent = pkg.code == currentPlan;
    return Card(
      margin: EdgeInsets.zero,
      color: featured ? colors.primary.withValues(alpha: 0.06) : null,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(12),
        side: featured
            ? BorderSide(color: colors.primary, width: 1.6)
            : BorderSide(color: colors.outlineVariant, width: 1),
      ),
      child: InkWell(
        borderRadius: BorderRadius.circular(12),
        // The Free plan cannot be bought; a paid plan stays tappable for
        // early renewal even while active.
        onTap: pkg.isFree ? null : onTap,
        child: Stack(
          children: <Widget>[
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
              child: Row(
                children: <Widget>[
                  Container(
                    width: 44,
                    height: 44,
                    decoration: BoxDecoration(
                      color: colors.primaryContainer,
                      borderRadius: BorderRadius.circular(10),
                    ),
                    child: Icon(
                      pkg.unlimited
                          ? Icons.all_inclusive
                          : Icons.toll_outlined,
                      color: colors.primary,
                    ),
                  ),
                  const SizedBox(width: 14),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: <Widget>[
                        Row(
                          children: <Widget>[
                            Text(
                              pkg.name,
                              style: const TextStyle(
                                fontWeight: FontWeight.w800,
                                fontSize: 16,
                              ),
                            ),
                            if (isCurrent) ...<Widget>[
                              const SizedBox(width: 8),
                              Container(
                                padding: const EdgeInsets.symmetric(
                                  horizontal: 8,
                                  vertical: 2,
                                ),
                                decoration: BoxDecoration(
                                  color: colors.secondaryContainer,
                                  borderRadius: BorderRadius.circular(999),
                                ),
                                child: Text(
                                  'CURRENT',
                                  style: TextStyle(
                                    fontSize: 10,
                                    fontWeight: FontWeight.w800,
                                    letterSpacing: 0.4,
                                    color: colors.onSecondaryContainer,
                                  ),
                                ),
                              ),
                            ],
                          ],
                        ),
                        const SizedBox(height: 2),
                        Text(
                          pkg.unlimited
                              ? '$_headline · fair-use applies'
                              : '$_headline · ${formatCredits(pkg.credits)} credits',
                          style: Theme.of(context).textTheme.bodySmall,
                        ),
                      ],
                    ),
                  ),
                  Text(
                    pkg.isFree ? 'Free' : formatVnd(pkg.priceVnd),
                    style: Theme.of(context).textTheme.titleMedium?.copyWith(
                      fontWeight: FontWeight.w700,
                      color: colors.primary,
                    ),
                  ),
                  const SizedBox(width: 6),
                  Icon(
                    pkg.isFree ? null : Icons.chevron_right,
                    color: colors.outline,
                  ),
                ],
              ),
            ),
            if (pkg.badge != null)
              Positioned(
                top: 0,
                right: 0,
                child: Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                  decoration: BoxDecoration(
                    color: colors.primaryContainer,
                    borderRadius: const BorderRadius.only(
                      topRight: Radius.circular(12),
                      bottomLeft: Radius.circular(12),
                    ),
                  ),
                  child: Text(
                    pkg.badge!.toUpperCase(),
                    style: TextStyle(
                      fontSize: 10,
                      fontWeight: FontWeight.w800,
                      letterSpacing: 0.4,
                      color: colors.onPrimaryContainer,
                    ),
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }
}
