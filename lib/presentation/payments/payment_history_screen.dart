/// Lịch sử thanh toán: danh sách đơn nạp + trạng thái.
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../domain/entities/payment_entities.dart';
import 'format_vnd.dart';
import 'payments_providers.dart';

class PaymentHistoryScreen extends ConsumerWidget {
  const PaymentHistoryScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final AsyncValue<List<PaymentOrder>> orders =
        ref.watch(paymentHistoryProvider);
    return Scaffold(
      appBar: AppBar(title: const Text('Payment history')),
      body: RefreshIndicator(
        onRefresh: () async => ref.refresh(paymentHistoryProvider.future),
        child: orders.when(
          data: (List<PaymentOrder> list) {
            if (list.isEmpty) {
              return ListView(
                children: <Widget>[
                  const SizedBox(height: 120),
                  Icon(
                    Icons.receipt_long_outlined,
                    size: 56,
                    color: Theme.of(context).colorScheme.outline,
                  ),
                  const SizedBox(height: 12),
                  Text(
                    'No transactions yet.\nTop up credits under "Buy credits".',
                    textAlign: TextAlign.center,
                    style: Theme.of(context).textTheme.bodyMedium,
                  ),
                ],
              );
            }
            return ListView.separated(
              padding: const EdgeInsets.fromLTRB(20, 12, 20, 24),
              itemCount: list.length,
              separatorBuilder: (_, _) => const SizedBox(height: 10),
              itemBuilder: (BuildContext context, int index) =>
                  _OrderTile(order: list[index]),
            );
          },
          loading: () => const Center(child: CircularProgressIndicator()),
          error: (Object e, StackTrace _) => ListView(
            children: <Widget>[
              const SizedBox(height: 80),
              Padding(
                padding: const EdgeInsets.all(24),
                child: Text(
                  '$e',
                  textAlign: TextAlign.center,
                  style: const TextStyle(color: Colors.red),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _OrderTile extends StatelessWidget {
  const _OrderTile({required this.order});

  final PaymentOrder order;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final bool paid = order.isPaid;
    return Card(
      margin: EdgeInsets.zero,
      child: ListTile(
        contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
        leading: Container(
          width: 40,
          height: 40,
          decoration: BoxDecoration(
            color: paid
                ? Colors.green.withValues(alpha: 0.12)
                : theme.colorScheme.surfaceContainerHighest,
            borderRadius: BorderRadius.circular(10),
          ),
          child: Icon(
            paid ? Icons.check_circle_outline : Icons.schedule,
            color: paid ? Colors.green.shade700 : theme.colorScheme.outline,
            size: 22,
          ),
        ),
        title: Text(
          '${formatCredits(order.credits)} credit · ${formatVnd(order.amountVnd)}',
          style: const TextStyle(fontWeight: FontWeight.w700),
        ),
        subtitle: Text(
          '${order.orderCode} · '
          '${order.createdAt.toLocal().toString().substring(0, 16)}',
        ),
        trailing: Text(
          paid ? 'Paid' : 'Awaiting transfer',
          style: theme.textTheme.labelLarge?.copyWith(
            color: paid ? Colors.green.shade700 : theme.colorScheme.outline,
            fontWeight: FontWeight.w700,
          ),
        ),
      ),
    );
  }
}
