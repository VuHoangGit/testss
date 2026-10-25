/// Gom N lời gọi refresh song song thành đúng 1 lần thật (EC-31).
///
/// Khi access vừa hết hạn, nhiều request có thể nhận 401 cùng lúc — nếu mỗi
/// request tự refresh thì tự gây ra race reuse refresh token (EC-11).
library;

class SessionRefresher {
  Future<void>? _inFlight;

  /// Các lời gọi chạy trong lúc 1 lần refresh đang bay sẽ đợi chung kết quả đó.
  Future<void> run(Future<void> Function() doRefresh) {
    final Future<void>? existing = _inFlight;
    if (existing != null) return existing;
    final Future<void> future = doRefresh().whenComplete(
      () => _inFlight = null,
    );
    _inFlight = future;
    return future;
  }
}
