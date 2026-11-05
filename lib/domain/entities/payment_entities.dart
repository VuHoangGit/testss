/// Entity thanh toán: gói credit, số dư, đơn nạp — thuần dữ liệu.
library;

class PricingPackage {
  const PricingPackage({
    required this.id,
    required this.code,
    required this.name,
    required this.priceVnd,
    required this.credits,
  });

  final int id;

  /// Mã ổn định gửi lên khi tạo đơn (vd "P1000").
  final String code;
  final String name;
  final int priceVnd;
  final int credits;
}

class CreditBalance {
  const CreditBalance({
    required this.free,
    required this.purchased,
    required this.monthlyFree,
    required this.aiCost,
  });

  /// Credit free của kỳ tháng này (reset đầu tháng).
  final int free;

  /// Credit nạp mua — không hết hạn.
  final int purchased;

  /// Mức free mỗi tháng (300) và giá mỗi lượt gọi AI (50).
  final int monthlyFree;
  final int aiCost;

  int get total => free + purchased;
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
    this.qrUrl,
    this.paidAt,
    this.bankBin = '',
    this.bankAccount = '',
    this.accountName = '',
  });

  final String id;

  /// "DVXXXXXX" — mã đối chiếu trong nội dung chuyển khoản.
  final String orderCode;

  /// pending | paid | cancelled.
  final String status;
  final int amountVnd;
  final int credits;
  final String transferContent;
  final DateTime createdAt;

  /// URL ảnh VietQR (null nếu backend chưa cấu hình số tài khoản).
  final String? qrUrl;
  final DateTime? paidAt;

  /// Thông tin tài khoản nhận (rỗng nếu chưa cấu hình phía backend).
  final String bankBin;
  final String bankAccount;
  final String accountName;

  bool get isPaid => status == 'paid';
}
