"""Giới hạn tần suất gọi API — cửa sổ trượt 60 giây, lưu trong bộ nhớ tiến trình.

Mục tiêu: chặn lạm dụng tốn tiền (mỗi lượt gọi AI là tiền thật trả cho nhà cung
cấp AI) và chặn spam upload/đơn nạp. Không thêm thư viện ngoài để solution vẫn
cài được offline.

Giới hạn: bộ đếm nằm trong RAM của TỪNG tiến trình — chạy nhiều worker (uvicorn
--workers N) thì mỗi worker đếm riêng, và restart là reset. Đủ cho 1 instance;
khi scale ngang phải thay bằng Redis (giữ nguyên interface `RateLimiter.hit`).
"""

from __future__ import annotations

import threading
import time
from collections import deque


class RateLimiter:
    """Bộ đếm cửa sổ trượt theo khoá (mỗi khoá = 1 user hoặc 1 IP)."""

    # Dọn bucket rỗng mỗi 5 phút để dict không phình theo số user từng gọi
    _CLEANUP_INTERVAL_SECONDS = 300.0

    def __init__(self, name: str) -> None:
        self.name = name
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()
        self._last_cleanup = 0.0

    def hit(self, key: str, max_calls: int, window_seconds: float) -> float | None:
        """Ghi nhận 1 lượt gọi.

        Trả `None` khi còn trong hạn mức (đã ghi lượt này), hoặc số giây phải
        chờ khi đã vượt `max_calls` trong `window_seconds` (KHÔNG ghi lượt).
        `max_calls <= 0` nghĩa là tắt giới hạn.
        """
        if max_calls <= 0 or window_seconds <= 0:
            return None

        now = time.monotonic()
        cutoff = now - window_seconds
        with self._lock:
            bucket = self._hits.get(key)
            if bucket is None:
                bucket = deque()
                self._hits[key] = bucket
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            if len(bucket) >= max_calls:
                # Lượt cũ nhất rời cửa sổ sau chừng này giây → chờ được
                return max(1.0, bucket[0] + window_seconds - now)
            bucket.append(now)
            self._cleanup(now, cutoff)
            return None

    def reset(self) -> None:
        """Xoá toàn bộ bộ đếm (test dùng để cô lập giữa các case)."""
        with self._lock:
            self._hits.clear()
            self._last_cleanup = 0.0

    def _cleanup(self, now: float, cutoff: float) -> None:
        """Bỏ các bucket đã rỗng — gọi trong lock, chạy tối đa 5 phút/lần."""
        if now - self._last_cleanup < self._CLEANUP_INTERVAL_SECONDS:
            return
        self._last_cleanup = now
        empty = [
            key
            for key, bucket in self._hits.items()
            if not bucket or bucket[-1] <= cutoff
        ]
        for key in empty:
            del self._hits[key]


_limiters: dict[str, RateLimiter] = {}
_limiters_lock = threading.Lock()


def get_limiter(name: str) -> RateLimiter:
    """Lấy (hoặc tạo) limiter dùng chung theo tên nhóm — vd "ai", "upload"."""
    with _limiters_lock:
        limiter = _limiters.get(name)
        if limiter is None:
            limiter = _limiters[name] = RateLimiter(name)
        return limiter


def reset_rate_limits() -> None:
    """Xoá bộ đếm của mọi nhóm (test dùng)."""
    with _limiters_lock:
        for limiter in _limiters.values():
            limiter.reset()
