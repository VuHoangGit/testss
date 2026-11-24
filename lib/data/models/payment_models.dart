/// JSON models for payments/plans — the backend speaks snake_case.
library;

import '../../domain/entities/payment_entities.dart';

class PricingPackageModel extends PricingPackage {
  const PricingPackageModel({
    required super.id,
    required super.code,
    required super.name,
    required super.priceVnd,
    required super.credits,
    super.badge,
    super.unlimited,
  });

  factory PricingPackageModel.fromJson(Map<String, dynamic> json) {
    return PricingPackageModel(
      id: (json['id'] as num?)?.toInt() ?? 0,
      code: json['code'] as String? ?? '',
      name: json['name'] as String? ?? '',
      priceVnd: (json['price_vnd'] as num?)?.toInt() ?? 0,
      credits: (json['credits'] as num?)?.toInt() ?? 0,
      badge: json['badge'] as String?,
      unlimited: json['unlimited'] as bool? ?? false,
    );
  }
}

class CreditBalanceModel extends CreditBalance {
  const CreditBalanceModel({
    required super.free,
    required super.purchased,
    required super.monthlyFree,
    required super.aiCost,
    super.planCode,
    super.unlimited,
    super.planExpiresAt,
  });

  factory CreditBalanceModel.fromJson(Map<String, dynamic> json) {
    return CreditBalanceModel(
      free: (json['free'] as num?)?.toInt() ?? 0,
      purchased: (json['purchased'] as num?)?.toInt() ?? 0,
      monthlyFree: (json['monthly_free'] as num?)?.toInt() ?? 0,
      aiCost: (json['ai_cost'] as num?)?.toInt() ?? 0,
      planCode: json['plan_code'] as String? ?? 'FREE',
      unlimited: json['unlimited'] as bool? ?? false,
      planExpiresAt: json['plan_expires_at'] == null
          ? null
          : DateTime.tryParse(json['plan_expires_at'] as String),
    );
  }
}

class PaymentOrderModel extends PaymentOrder {
  const PaymentOrderModel({
    required super.id,
    required super.orderCode,
    required super.status,
    required super.amountVnd,
    required super.credits,
    required super.transferContent,
    required super.createdAt,
    super.planCode,
    super.qrUrl,
    super.paidAt,
    super.bankBin,
    super.bankAccount,
    super.accountName,
  });

  factory PaymentOrderModel.fromJson(Map<String, dynamic> json) {
    return PaymentOrderModel(
      id: json['id'] as String? ?? '',
      orderCode: json['order_code'] as String? ?? '',
      status: json['status'] as String? ?? 'pending',
      amountVnd: (json['amount_vnd'] as num?)?.toInt() ?? 0,
      credits: (json['credits'] as num?)?.toInt() ?? 0,
      transferContent: json['transfer_content'] as String? ?? '',
      planCode: json['plan_code'] as String? ?? '',
      qrUrl: json['qr_url'] as String?,
      createdAt: DateTime.tryParse(json['created_at'] as String? ?? '') ??
          DateTime.fromMillisecondsSinceEpoch(0),
      paidAt: json['paid_at'] == null
          ? null
          : DateTime.tryParse(json['paid_at'] as String),
      bankBin: (json['bank_bin'] as String?) ?? '',
      bankAccount: (json['bank_account'] as String?) ?? '',
      accountName: (json['account_name'] as String?) ?? '',
    );
  }
}
