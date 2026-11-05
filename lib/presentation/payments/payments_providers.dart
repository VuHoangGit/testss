/// Provider cho credit + thanh toán.
library;

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../data/repositories/payments_repository_impl.dart';
import '../../domain/entities/payment_entities.dart';
import '../../domain/repositories/payments_repository.dart';
import '../providers.dart';

final Provider<PaymentsRepository> paymentsRepositoryProvider =
    Provider<PaymentsRepository>(
      (Ref ref) => PaymentsRepositoryImpl(dio: ref.watch(apiDioProvider)),
    );

/// Số dư credit — invalidate sau khi nạp thành công để refresh mọi chỗ dùng.
final FutureProvider<CreditBalance> creditBalanceProvider =
    FutureProvider<CreditBalance>(
      (Ref ref) => ref.watch(paymentsRepositoryProvider).getBalance(),
    );

/// Bảng giá gói credit.
final FutureProvider<List<PricingPackage>> pricingPackagesProvider =
    FutureProvider<List<PricingPackage>>(
      (Ref ref) => ref.watch(paymentsRepositoryProvider).listPackages(),
    );

/// Lịch sử thanh toán — Riverpod 3 provider mặc định autoDispose, mỗi lần
/// vào màn lại fetch dữ liệu mới.
final FutureProvider<List<PaymentOrder>> paymentHistoryProvider =
    FutureProvider<List<PaymentOrder>>(
      (Ref ref) => ref.watch(paymentsRepositoryProvider).listOrders(),
    );
