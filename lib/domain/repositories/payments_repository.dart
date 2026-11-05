/// Hợp đồng tầng domain cho credit + thanh toán.
library;

import '../entities/payment_entities.dart';

abstract interface class PaymentsRepository {
  Future<List<PricingPackage>> listPackages();

  Future<CreditBalance> getBalance();

  /// Tạo đơn nạp theo mã gói → trả mã đơn + QR + nội dung chuyển khoản.
  Future<PaymentOrder> createOrder(String packageCode);

  Future<PaymentOrder> getOrder(String orderId);

  /// Lịch sử thanh toán (mới nhất trước).
  Future<List<PaymentOrder>> listOrders();
}
