"""Client-side throttling for outbound Mistral API calls.

Mistral enforces requests-per-second and tokens-per-minute limits independently per
account tier, exposes no remaining-quota header, and returns HTTP 429 (with a
`Retry-After` header) once a limit is exceeded. `AIClient` used to fire calls straight
from ingestion's per-article loop with no pacing at all, so a company with several new
articles could burst past the per-second limit within a fraction of a second.

`MistralRateLimiter` fixes the root cause by spacing every outbound call at least
`1 / max_requests_per_second` apart. It's lock-protected so pacing is correct even when
multiple ingestion runs execute in different threads of the same process at once (e.g. a
manual trigger racing the scheduler) — see `get_shared_rate_limiter`, which hands out one
instance per process so every `AIClient` paces against the same clock.
"""

import threading
import time
from typing import Callable


class MistralRateLimiter:
    def __init__(
        self,
        max_requests_per_second: float,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ):
        if max_requests_per_second <= 0:
            raise ValueError("max_requests_per_second must be > 0")
        self._min_interval = 1.0 / max_requests_per_second
        self._clock = clock
        self._sleep = sleep
        self._lock = threading.Lock()
        self._next_slot = 0.0

    def acquire(self) -> None:
        """Blocks until it's this caller's turn, then reserves the next slot.

        Slot reservation happens under the lock; the actual sleep happens outside it so
        one thread waiting doesn't hold up another thread's slot bookkeeping.
        """
        with self._lock:
            now = self._clock()
            start = max(now, self._next_slot)
            self._next_slot = start + self._min_interval
        wait = start - now
        if wait > 0:
            self._sleep(wait)


_shared_lock = threading.Lock()
_shared_limiter: MistralRateLimiter | None = None


def get_shared_rate_limiter(max_requests_per_second: float) -> MistralRateLimiter:
    """Returns a process-wide limiter, creating it on first call.

    Every `AIClient` that doesn't get an explicit `rate_limiter` shares this instance —
    a fresh `AIClient` is constructed per ingestion run, but they all must throttle
    against the same real request rate to Mistral, not just calls within their own run.
    The configured rate only takes effect on the first call in a process's lifetime,
    matching how `get_settings()` is itself cached for the process lifetime.
    """
    global _shared_limiter
    with _shared_lock:
        if _shared_limiter is None:
            _shared_limiter = MistralRateLimiter(max_requests_per_second)
        return _shared_limiter
