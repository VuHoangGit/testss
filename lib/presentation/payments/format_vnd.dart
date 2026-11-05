/// Định dạng số tiền kiểu Việt Nam: 100000 → "100.000₫".
library;

String formatVnd(int amount) {
  final String digits = amount.abs().toString();
  final StringBuffer out = StringBuffer();
  for (int i = 0; i < digits.length; i++) {
    final int remaining = digits.length - i;
    out.write(digits[i]);
    // Chèn dấu chấm sau mỗi nhóm 3 chữ số (từ phải sang trái)
    if (remaining > 1 && remaining % 3 == 1) {
      out.write('.');
    }
  }
  return '${amount < 0 ? '-' : ''}${out.toString()}₫';
}

/// 1000 → "1.000" — dùng cho số credit cho dễ đọc.
String formatCredits(int credits) {
  final String digits = credits.toString();
  final StringBuffer out = StringBuffer();
  for (int i = 0; i < digits.length; i++) {
    final int remaining = digits.length - i;
    out.write(digits[i]);
    if (remaining > 1 && remaining % 3 == 1) {
      out.write('.');
    }
  }
  return out.toString();
}
