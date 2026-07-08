import threading
import time

import pytest

from app.services.mistral_rate_limiter import MistralRateLimiter, get_shared_rate_limiter


class _FakeClock:
    """A controllable clock/sleep pair so pacing tests don't burn real wall-clock time
    and don't depend on scheduler jitter."""

    def __init__(self):
        self.now = 0.0

    def time(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


def test_first_acquire_does_not_wait():
    clock = _FakeClock()
    limiter = MistralRateLimiter(2.0, clock=clock.time, sleep=clock.sleep)
    limiter.acquire()
    assert clock.now == 0.0


def test_acquire_spaces_calls_by_min_interval():
    clock = _FakeClock()
    limiter = MistralRateLimiter(2.0, clock=clock.time, sleep=clock.sleep)  # 0.5s apart

    limiter.acquire()
    assert clock.now == pytest.approx(0.0)
    limiter.acquire()
    assert clock.now == pytest.approx(0.5)
    limiter.acquire()
    assert clock.now == pytest.approx(1.0)


def test_acquire_does_not_wait_if_caller_is_already_slower_than_the_limit():
    clock = _FakeClock()
    limiter = MistralRateLimiter(2.0, clock=clock.time, sleep=clock.sleep)  # 0.5s apart

    limiter.acquire()
    clock.now = 10.0  # caller took its own sweet time between calls
    limiter.acquire()
    assert clock.now == pytest.approx(10.0)  # no catch-up penalty


def test_rejects_non_positive_rate():
    with pytest.raises(ValueError):
        MistralRateLimiter(0)
    with pytest.raises(ValueError):
        MistralRateLimiter(-1.0)


def test_acquire_is_thread_safe_and_paces_concurrent_callers():
    # Real threads + real clock (not the fake one) — a high rate keeps this fast while
    # still proving no two callers get the same slot.
    limiter = MistralRateLimiter(200.0)  # 5ms apart
    starts: list[float] = []
    lock = threading.Lock()

    def worker():
        limiter.acquire()
        with lock:
            starts.append(time.monotonic())

    threads = [threading.Thread(target=worker) for _ in range(10)]
    t0 = time.monotonic()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    elapsed = time.monotonic() - t0

    # 10 calls at 200/s must take at least 9 * 5ms, with generous slack for scheduling.
    assert elapsed >= 0.9 * (9 / 200.0)
    assert len(starts) == 10


def test_get_shared_rate_limiter_returns_singleton():
    first = get_shared_rate_limiter(3.0)
    second = get_shared_rate_limiter(999.0)  # rate ignored once the singleton exists
    assert first is second
