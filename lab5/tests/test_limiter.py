from concurrent.futures import ThreadPoolExecutor

import pytest

from src.limiter import MemoryRateLimiter, RateLimitExceeded


def test_window_expires_at_exact_boundary():
    now = [0.0]
    limiter = MemoryRateLimiter(1, 60, clock=lambda: now[0])
    limiter.check("A")
    now[0] = 59.1
    with pytest.raises(RateLimitExceeded) as error:
        limiter.check("A")
    assert error.value.retry_after == 1
    now[0] = 60.0
    limiter.check("A")


def test_rejection_does_not_extend_window():
    now = [0.0]
    limiter = MemoryRateLimiter(2, 60, clock=lambda: now[0])
    limiter.check("A")
    now[0] = 10
    limiter.check("A")
    now[0] = 20.1
    with pytest.raises(RateLimitExceeded) as error:
        limiter.check("A")
    assert error.value.retry_after == 40
    assert len(limiter.history["A"]) == 2
    now[0] = 60
    limiter.check("A")
    assert list(limiter.history["A"]) == [10, 60]


def test_clients_have_independent_history():
    limiter = MemoryRateLimiter(1, clock=lambda: 0)
    limiter.check("A")
    limiter.check("B")
    with pytest.raises(RateLimitExceeded):
        limiter.check("A")


def test_concurrent_admission_is_atomic():
    limiter = MemoryRateLimiter(3, clock=lambda: 0)
    def check(_):
        try:
            limiter.check("A")
            return True
        except RateLimitExceeded:
            return False
    with ThreadPoolExecutor(max_workers=12) as pool:
        assert sum(pool.map(check, range(40))) == 3


@pytest.mark.parametrize("limit,window", [(0, 60), (True, 60), (1.5, 60), (1, 0), (1, -1), (1, float("nan")), (1, float("inf"))])
def test_invalid_parameters(limit, window):
    with pytest.raises(ValueError):
        MemoryRateLimiter(limit, window)
