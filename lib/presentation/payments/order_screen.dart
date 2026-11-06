/// Màn thanh toán đơn nạp: QR + nội dung chuyển khoản, tự poll đến khi paid.
library;

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../domain/entities/payment_entities.dart';
import 'format_vnd.dart';
import 'payments_providers.dart';

class OrderScreen extends ConsumerStatefulWidget {
  const OrderScreen({super.key, required this.order});

  final PaymentOrder order;

  @override
  ConsumerState<OrderScreen> createState() => _OrderScreenState();
}

class _OrderScreenState extends ConsumerState<OrderScreen> {
  late PaymentOrder _order;
  Timer? _poll;

  @override
  void initState() {
    super.initState();
    _order = widget.order;
    // Cứ 4s hỏi trạng thái đơn — SePay nhận chuyển khoản sẽ đổi paid
    _poll = Timer.periodic(const Duration(seconds: 4), (_) => _refresh());
  }

  @override
  void dispose() {
    _poll?.cancel();
    super.dispose();
  }

  Future<void> _refresh() async {
    if (_order.isPaid || !mounted) return;
    try {
      final PaymentOrder latest =
          await ref.read(paymentsRepositoryProvider).getOrder(_order.id);
      if (!mounted) return;
      setState(() => _order = latest);
      if (latest.isPaid) {
        ref.invalidate(creditBalanceProvider);
        ref.invalidate(paymentHistoryProvider);
      }
    } on Exception {
      // Mất mạng tạm thời — giữ nguyên, lượt poll sau thử lại
    }
  }

  void _copy(String value, String label) {
    Clipboard.setData(ClipboardData(text: value));
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(SnackBar(content: Text('Copied $label')));
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return Scaffold(
      appBar: AppBar(title: const Text('Payment')),
      body: SingleChildScrollView(
        padding: const EdgeInsets.fromLTRB(20, 12, 20, 24),
        child: _order.isPaid ? _buildPaid(theme) : _buildPending(theme),
      ),
    );
  }

  Widget _buildPending(ThemeData theme) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: <Widget>[
            const SizedBox(
              width: 14,
              height: 14,
              child: CircularProgressIndicator(strokeWidth: 2),
            ),
            const SizedBox(width: 8),
            Text(
              'Waiting for the transfer…',
              style: theme.textTheme.titleMedium,
            ),
          ],
        ),
        const SizedBox(height: 4),
        Text(
          'Scan the QR code or transfer with the exact content below — credits are '
          'added to your account within seconds.',
          textAlign: TextAlign.center,
          style: theme.textTheme.bodySmall?.copyWith(
            color: theme.colorScheme.onSurfaceVariant,
          ),
        ),
        const SizedBox(height: 16),
        if (_order.qrUrl != null) ...<Widget>[
          Center(
            child: ClipRRect(
              borderRadius: BorderRadius.circular(12),
              child: Image.network(
                _order.qrUrl!,
                width: 220,
                height: 220,
                fit: BoxFit.contain,
                errorBuilder: (_, Object e, StackTrace? st) => const SizedBox(
                  width: 220,
                  height: 90,
                  child: Center(
                    child: Text('Could not load the QR image — use the details below'),
                  ),
                ),
              ),
            ),
          ),
          const SizedBox(height: 16),
        ] else
          Padding(
            padding: const EdgeInsets.only(bottom: 8),
            child: Text(
              'QR image is not available yet (the backend is missing SEPAY_BANK_ACCOUNT) — '
              'transfer using the details below.',
              textAlign: TextAlign.center,
              style: theme.textTheme.bodySmall?.copyWith(
                color: theme.colorScheme.onSurfaceVariant,
              ),
            ),
          ),
        const SizedBox(height: 8),
        Card(
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
            child: Column(
              children: <Widget>[
                _infoRow(
                  theme,
                  icon: Icons.account_balance,
                  label: 'Bank',
                  value: _order.bankBin.isEmpty ? 'MB Bank' : _order.bankBin,
                ),
                if (_order.accountName.isNotEmpty)
                  _infoRow(
                    theme,
                    icon: Icons.person_outline,
                    label: 'Account holder',
                    value: _order.accountName,
                  ),
                if (_order.bankAccount.isNotEmpty)
                  _infoRow(
                    theme,
                    icon: Icons.credit_card,
                    label: 'Account number',
                    value: _order.bankAccount,
                    onCopy: () => _copy(_order.bankAccount, 'account number'),
                  ),
                _infoRow(
                  theme,
                  icon: Icons.payments_outlined,
                  label: 'Amount',
                  value: formatVnd(_order.amountVnd),
                  onCopy: () =>
                      _copy(_order.amountVnd.toString(), 'amount'),
                ),
                _infoRow(
                  theme,
                  icon: Icons.sticky_note_2_outlined,
                  label: 'Transfer content',
                  value: _order.transferContent,
                  highlight: true,
                  onCopy: () =>
                      _copy(_order.transferContent, 'transfer content'),
                ),
              ],
            ),
          ),
        ),
        const SizedBox(height: 8),
        Text(
          'A transfer with the wrong amount or without the order code will not add credits.',
          textAlign: TextAlign.center,
          style: theme.textTheme.bodySmall?.copyWith(
            color: theme.colorScheme.outline,
          ),
        ),
      ],
    );
  }

  Widget _infoRow(
    ThemeData theme, {
    required IconData icon,
    required String label,
    required String value,
    bool highlight = false,
    VoidCallback? onCopy,
  }) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: Row(
        children: <Widget>[
          Icon(icon, size: 20, color: theme.colorScheme.primary),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Text(
                  label.toUpperCase(),
                  style: theme.textTheme.labelSmall?.copyWith(
                    letterSpacing: 0.8,
                    color: theme.colorScheme.outline,
                  ),
                ),
                Text(
                  value,
                  style: highlight
                      ? const TextStyle(
                          fontWeight: FontWeight.w800,
                          fontSize: 16,
                        )
                      : theme.textTheme.bodyLarge,
                ),
              ],
            ),
          ),
          if (onCopy != null)
            IconButton(
              tooltip: 'Copy',
              onPressed: onCopy,
              icon: const Icon(Icons.copy, size: 18),
            ),
        ],
      ),
    );
  }

  Widget _buildPaid(ThemeData theme) {
    return Column(
      children: <Widget>[
        const SizedBox(height: 24),
        Icon(
          Icons.check_circle,
          color: Colors.green.shade600,
          size: 72,
        ),
        const SizedBox(height: 12),
        Text('Payment successful!', style: theme.textTheme.titleLarge),
        const SizedBox(height: 4),
        Text(
          'Added ${formatCredits(_order.credits)} credits to your account.',
          style: theme.textTheme.bodyMedium,
        ),
        const SizedBox(height: 24),
        FilledButton.icon(
          onPressed: () => Navigator.of(context).pop(),
          icon: const Icon(Icons.done),
          label: const Text('Done'),
        ),
      ],
    );
  }
}
