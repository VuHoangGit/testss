/// Payment entities: subscription plans, credit balance, orders — pure data.
library;

class PricingPackage {
  const PricingPackage({
    required this.id,
    required this.code,
    required this.name,
    required this.priceVnd,
    required this.credits,
    this.badge,
    this.unlimited = false,
  });

  final int id;

  /// Stable code sent when creating an order (e.g. "PLUS").
  final String code;
  final String name;
  final int priceVnd;

  /// Monthly credit quota of the plan (not a one-time credit top-up).
  final int credits;

  /// Marketing label ("Most popular") — null when the plan has none.
  final String? badge;

  /// Max plan: the UI shows "Unlimited" instead of a credit count, plus a
  /// small fair-use footnote.
  final bool unlimited;

  /// Plan highlighted on the Plans screen (border + tinted background).
  bool get isFeatured => code == 'PRO';

  /// The default plan — not purchasable, shown for comparison.
  bool get isFree => code == 'FREE';
}

class CreditBalance {
  const CreditBalance({
    required this.free,
    required this.purchased,
    required this.monthlyFree,
    required this.aiCost,
    this.planCode = 'FREE',
    this.unlimited = false,
    this.planExpiresAt,
  });

  /// Remaining credits of this month's quota (resets each period).
  final int free;

  /// Legacy purchased credits — never expire, spent after the monthly quota.
  final int purchased;

  /// Current plan's monthly quota, and the cost per AI call (50).
  final int monthlyFree;
  final int aiCost;

  /// Effective plan (FREE when expired) and its expiry timestamp.
  final String planCode;
  final bool unlimited;
  final DateTime? planExpiresAt;

  int get total => free + purchased;

  /// Days left before the plan expires (null = Free plan, no expiry).
  int? get daysRemaining {
    final DateTime? expiry = planExpiresAt;
    if (expiry == null || planCode == 'FREE') return null;
    final int days = expiry.difference(DateTime.now()).inDays;
    return days < 0 ? 0 : days;
  }

  /// Expiring soon (≤3 days) — the UI shows a yellow renewal banner.
  bool get expiringSoon {
    final int? days = daysRemaining;
    return days != null && days <= 3;
  }
}

class PaymentOrder {
  const PaymentOrder({
    required this.id,
    required this.orderCode,
    required this.status,
    required this.amountVnd,
    required this.credits,
    required this.transferContent,
    required this.createdAt,
    this.planCode = '',
    this.qrUrl,
    this.paidAt,
    this.bankBin = '',
    this.bankAccount = '',
    this.accountName = '',
  });

  final String id;

  /// "DVXXXXXX" — the matching code inside the bank transfer content.
  final String orderCode;

  /// pending | paid | cancelled.
  final String status;
  final int amountVnd;
  final int credits;

  /// Subscription plan bought by this order (PLUS/PRO/MAX; empty = legacy
  /// credit order created before the plan migration).
  final String planCode;
  final String transferContent;
  final DateTime createdAt;

  /// VietQR image URL (null when the backend has no receiving account set).
  final String? qrUrl;
  final DateTime? paidAt;

  /// Receiving account info (empty when unconfigured on the backend).
  final String bankBin;
  final String bankAccount;
  final String accountName;

  bool get isPaid => status == 'paid';
}
