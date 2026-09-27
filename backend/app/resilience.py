"""Reusable timeout-adjacent retry, jitter, circuit breaker, and TTL cache policies."""
from collections.abc import Callable
from dataclasses import dataclass
import random
from threading import Lock
import time
import uuid
from typing import Any, Generic, TypeVar

from backend.app.errors import CircuitOpenError
from backend.app.observability import bind_provider_attempt, metrics, trace_span


T = TypeVar('T')


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3
    base_delay_seconds: float = 0.25
    max_delay_seconds: float = 5.0
    jitter_ratio: float = 0.25

    def delay(self, completed_attempt: int, random_value: float) -> float:
        base = min(
            self.max_delay_seconds,
            self.base_delay_seconds * (2 ** max(0, completed_attempt - 1)),
        )
        jitter = base * self.jitter_ratio * ((random_value * 2) - 1)
        return max(0.0, base + jitter)


class CircuitBreaker:
    def __init__(
        self,
        name: str,
        *,
        failure_threshold: int = 5,
        recovery_seconds: float = 30.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if failure_threshold < 1 or recovery_seconds < 0:
            raise ValueError('Circuit breaker policy is invalid.')
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_seconds = recovery_seconds
        self._clock = clock
        self._lock = Lock()
        self._failures = 0
        self._opened_at: float | None = None
        self._half_open_in_flight = False

    def allow(self) -> None:
        with self._lock:
            if self._opened_at is None:
                return
            if self._clock() - self._opened_at < self.recovery_seconds:
                metrics.increment('smartwealth_circuit_rejections_total')
                raise CircuitOpenError(self.name)
            if self._half_open_in_flight:
                raise CircuitOpenError(self.name)
            self._half_open_in_flight = True

    def success(self) -> None:
        with self._lock:
            self._failures = 0
            self._opened_at = None
            self._half_open_in_flight = False

    def failure(self) -> None:
        with self._lock:
            self._failures += 1
            self._half_open_in_flight = False
            if self._failures >= self.failure_threshold:
                self._opened_at = self._clock()
                metrics.increment('smartwealth_circuit_opened_total')

    @property
    def state(self) -> str:
        with self._lock:
            if self._opened_at is None:
                return 'closed'
            if self._clock() - self._opened_at >= self.recovery_seconds:
                return 'half_open'
            return 'open'


class TTLCache(Generic[T]):
    def __init__(self, ttl_seconds: float, max_entries: int = 256) -> None:
        self.ttl_seconds = ttl_seconds
        self.max_entries = max_entries
        self._lock = Lock()
        self._items: dict[str, tuple[float, T]] = {}

    def get(self, key: str) -> T | None:
        now = time.monotonic()
        with self._lock:
            item = self._items.get(key)
            if item is None:
                metrics.increment('smartwealth_cache_misses_total')
                return None
            expires_at, value = item
            if expires_at <= now:
                self._items.pop(key, None)
                metrics.increment('smartwealth_cache_misses_total')
                return None
            metrics.increment('smartwealth_cache_hits_total')
            return value

    def set(self, key: str, value: T) -> None:
        with self._lock:
            if len(self._items) >= self.max_entries and key not in self._items:
                oldest = min(self._items, key=lambda item: self._items[item][0])
                self._items.pop(oldest, None)
            self._items[key] = (time.monotonic() + self.ttl_seconds, value)

    def clear(self) -> None:
        with self._lock:
            self._items.clear()


def call_with_resilience(
    operation: Callable[[], T],
    *,
    name: str,
    policy: RetryPolicy,
    breaker: CircuitBreaker,
    is_retryable: Callable[[Exception], bool],
    sleep: Callable[[float], None] = time.sleep,
    random_value: Callable[[], float] = random.random,
    on_attempt: Callable[[str, int], None] | None = None,
) -> T:
    last_error: Exception | None = None
    for attempt in range(1, policy.max_attempts + 1):
        breaker.allow()
        attempt_id = uuid.uuid4().hex
        if on_attempt is not None:
            on_attempt(attempt_id, attempt)
        with bind_provider_attempt(attempt_id), trace_span(
            'provider_call',
            provider_operation=name,
            attempt=attempt,
        ):
            try:
                result = operation()
            except Exception as error:
                last_error = error
                breaker.failure()
                metrics.increment('smartwealth_provider_failures_total')
                if attempt >= policy.max_attempts or not is_retryable(error):
                    raise
                sleep(policy.delay(attempt, random_value()))
            else:
                breaker.success()
                metrics.increment('smartwealth_provider_calls_total')
                return result
    assert last_error is not None
    raise last_error
