/// Màn chọn gói credit: số dư hiện tại + danh sách gói nạp (từ backend) → tạo đơn.
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../domain/entities/payment_entities.dart';
import 'format_vnd.dart';
import 'order_screen.dart';
import 'payments_providers.dart';

class PricingScreen extends ConsumerWidget {
  const PricingScreen({super.key});

  Future<void> _buyPackage(
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
      // Về từ màn thanh toán (đã paid hoặc đóng) → refresh số dư
      ref.invalidate(creditBalanceProvider);
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

    return Scaffold(
      appBar: AppBar(title: const Text('Buy credit')),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(20, 12, 20, 24),
        children: <Widget>[
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: balance.when(
                data: (CreditBalance b) => Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: <Widget>[
                    Text(
                      '${formatCredits(b.total)} credit',
                      style: Theme.of(context).textTheme.headlineSmall
                          ?.copyWith(
                            fontWeight: FontWeight.w800,
                            color: Theme.of(context).colorScheme.primary,
                          ),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      'Free this period: ${formatCredits(b.free)}/${formatCredits(b.monthlyFree)}'
                      ' · Purchased: ${formatCredits(b.purchased)}'
                      ' · Per AI call: ${b.aiCost} credits',
                      style: Theme.of(context).textTheme.bodySmall,
                    ),
                    const SizedBox(height: 4),
                    Text(
                      'The 300 free credits reset at the start of each month. '
                      'Purchased credits never expire.',
                      style: Theme.of(context).textTheme.bodySmall?.copyWith(
                        color: Theme.of(context).colorScheme.onSurfaceVariant,
                      ),
                    ),
                  ],
                ),
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
            'CHOOSE A TOP-UP PACKAGE',
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
                    child: _PackageCard(
                      pkg: p,
                      onTap: () => _buyPackage(context, ref, p.code),
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
        ],
      ),
    );
  }
}

class _PackageCard extends StatelessWidget {
  const _PackageCard({required this.pkg, required this.onTap});

  final PricingPackage pkg;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: EdgeInsets.zero,
      child: InkWell(
        borderRadius: BorderRadius.circular(12),
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
          child: Row(
            children: <Widget>[
              Container(
                width: 44,
                height: 44,
                decoration: BoxDecoration(
                  color: Theme.of(context).colorScheme.primaryContainer,
                  borderRadius: BorderRadius.circular(10),
                ),
                child: Icon(
                  Icons.toll_outlined,
                  color: Theme.of(context).colorScheme.primary,
                ),
              ),
              const SizedBox(width: 14),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: <Widget>[
                    Text(
                      '${formatCredits(pkg.credits)} credit',
                      style: const TextStyle(
                        fontWeight: FontWeight.w800,
                        fontSize: 16,
                      ),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      pkg.name,
                      style: Theme.of(context).textTheme.bodySmall,
                    ),
                  ],
                ),
              ),
              Text(
                formatVnd(pkg.priceVnd),
                style: Theme.of(context).textTheme.titleMedium?.copyWith(
                  fontWeight: FontWeight.w700,
                  color: Theme.of(context).colorScheme.primary,
                ),
              ),
              const SizedBox(width: 6),
              Icon(
                Icons.chevron_right,
                color: Theme.of(context).colorScheme.outline,
              ),
            ],
          ),
        ),
      ),
    );
  }
}
