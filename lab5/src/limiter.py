"""Скользящее окно для известных клиентов одного процесса."""
from collections import defaultdict, deque
from math import ceil, isfinite
from threading import Lock
from time import monotonic


class RateLimitExceeded(Exception):
    def __init__(self, retry_after: int):
        self.retry_after = retry_after
        super().__init__("Лимит запросов исчерпан")


class MemoryRateLimiter:
    def __init__(self, limit=60, window_seconds=60, clock=monotonic):
        if (not isinstance(limit, int) or isinstance(limit, bool) or limit < 1
                or not isfinite(window_seconds) or window_seconds <= 0):
            raise ValueError("Некорректные параметры ограничителя")
        self.limit = limit
        self.window = window_seconds
        self.clock = clock
        self.history = defaultdict(deque)
        self.lock = Lock()

    def check(self, client_id: str):
        with self.lock:
            now = self.clock()
            recent = self.history[client_id]
            while recent and recent[0] <= now - self.window:
                recent.popleft()
            if len(recent) >= self.limit:
                raise RateLimitExceeded(max(1, ceil(recent[0] + self.window - now)))
            recent.append(now)
