from concurrent.futures import Future, ThreadPoolExecutor
from threading import BoundedSemaphore, Lock
from typing import Any, Callable


class BoundedRunExecutor:
    """Thread pool with a hard cap on running plus queued work."""

    def __init__(self, max_workers: int, queue_capacity: int):
        if max_workers <= 0:
            raise ValueError('max_workers must be positive.')
        if queue_capacity < 0:
            raise ValueError('queue_capacity cannot be negative.')
        self.max_workers = max_workers
        self.queue_capacity = queue_capacity
        self._capacity = BoundedSemaphore(max_workers + queue_capacity)
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix='smartwealth-run',
        )
        self._lock = Lock()
        self._accepting = True
        self._futures: set[Future[Any]] = set()
        self._reserved = 0
        self._running = 0

    def reserve(self) -> bool:
        with self._lock:
            if not self._accepting:
                return False
        reserved = self._capacity.acquire(blocking=False)
        if reserved:
            with self._lock:
                self._reserved += 1
        return reserved

    def release_reservation(self) -> None:
        with self._lock:
            self._reserved = max(0, self._reserved - 1)
        self._capacity.release()

    def submit_reserved(
        self,
        function: Callable[..., Any],
        *args: Any,
    ) -> Future[Any]:
        with self._lock:
            if not self._accepting:
                raise RuntimeError('Run executor is shutting down.')
            self._reserved = max(0, self._reserved - 1)

            def tracked():
                with self._lock:
                    self._running += 1
                try:
                    return function(*args)
                finally:
                    with self._lock:
                        self._running = max(0, self._running - 1)

            try:
                future = self._executor.submit(tracked)
            except Exception:
                raise
            self._futures.add(future)

        def finished(completed: Future[Any]) -> None:
            self._capacity.release()
            with self._lock:
                self._futures.discard(completed)

        future.add_done_callback(finished)
        return future

    def shutdown(self, *, wait: bool = True) -> None:
        with self._lock:
            self._accepting = False
        self._executor.shutdown(wait=wait, cancel_futures=True)

    @property
    def accepting(self) -> bool:
        with self._lock:
            return self._accepting

    def snapshot(self) -> dict[str, int | bool]:
        with self._lock:
            submitted = len(self._futures)
            return {
                'accepting': self._accepting,
                'running': self._running,
                'queued': max(0, submitted - self._running),
                'reserved': submitted + self._reserved,
                'max_workers': self.max_workers,
                'queue_capacity': self.queue_capacity,
            }
