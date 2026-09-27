"""Dependency-light structured logs, metrics, and trace spans."""
from collections import defaultdict
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
import json
import logging
import sys
from threading import Lock
import time
import uuid
from typing import Any, Iterator

from backend.app.security import correlation_id_context


run_id_context: ContextVar[str] = ContextVar('run_id', default='unassigned')
trace_id_context: ContextVar[str] = ContextVar('trace_id', default='unassigned')
provider_attempt_context: ContextVar[str] = ContextVar(
    'provider_attempt_id',
    default='unassigned',
)


class JsonFormatter(logging.Formatter):
    RESERVED = set(logging.makeLogRecord({}).__dict__) | {'message', 'asctime'}

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'level': record.levelname.lower(),
            'logger': record.name,
            'message': record.getMessage(),
            'request_id': correlation_id_context.get(),
            'trace_id': trace_id_context.get(),
            'run_id': run_id_context.get(),
            'provider_attempt_id': provider_attempt_context.get(),
        }
        for key, value in record.__dict__.items():
            if key not in self.RESERVED and not key.startswith('_'):
                payload[key] = value
        if record.exc_info:
            payload['exception_type'] = record.exc_info[0].__name__
        return json.dumps(payload, default=str, separators=(',', ':'))


def configure_logging(level: str = 'INFO') -> None:
    root = logging.getLogger()
    root.setLevel(level.upper())
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root.handlers[:] = [handler]


class MetricRegistry:
    """Small in-process Prometheus registry without high-cardinality labels."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._counters: dict[str, float] = defaultdict(float)
        self._gauges: dict[str, float] = defaultdict(float)
        self._histograms: dict[str, tuple[int, float, float]] = {}

    @staticmethod
    def _name(name: str) -> str:
        clean = ''.join(char if char.isalnum() or char in '_:' else '_' for char in name)
        if not clean or clean[0].isdigit():
            raise ValueError('Metric names must begin with a letter or underscore.')
        return clean

    def increment(self, name: str, amount: float = 1.0) -> None:
        key = self._name(name)
        with self._lock:
            self._counters[key] += amount

    def gauge(self, name: str, value: float) -> None:
        key = self._name(name)
        with self._lock:
            self._gauges[key] = float(value)

    def observe(self, name: str, value: float) -> None:
        key = self._name(name)
        with self._lock:
            count, total, maximum = self._histograms.get(key, (0, 0.0, 0.0))
            self._histograms[key] = (
                count + 1,
                total + float(value),
                max(maximum, float(value)),
            )

    def snapshot(self) -> dict[str, dict[str, Any]]:
        with self._lock:
            return {
                'counters': dict(self._counters),
                'gauges': dict(self._gauges),
                'histograms': {
                    name: {'count': count, 'sum': total, 'max': maximum}
                    for name, (count, total, maximum) in self._histograms.items()
                },
            }

    def render_prometheus(self) -> str:
        snapshot = self.snapshot()
        lines: list[str] = []
        for name, value in sorted(snapshot['counters'].items()):
            lines.extend((f'# TYPE {name} counter', f'{name} {value:g}'))
        for name, value in sorted(snapshot['gauges'].items()):
            lines.extend((f'# TYPE {name} gauge', f'{name} {value:g}'))
        for name, value in sorted(snapshot['histograms'].items()):
            lines.extend((
                f'# TYPE {name} summary',
                f'{name}_count {value["count"]}',
                f'{name}_sum {value["sum"]:g}',
                f'{name}_max {value["max"]:g}',
            ))
        return '\n'.join(lines) + ('\n' if lines else '')

    def reset(self) -> None:
        with self._lock:
            self._counters.clear()
            self._gauges.clear()
            self._histograms.clear()


metrics = MetricRegistry()
logger = logging.getLogger('smartwealth.trace')


class ObservabilityMiddleware:
    def __init__(self, app: Any):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            await self.app(scope, receive, send)
            return
        path = scope.get('path', '')
        method = scope.get('method', 'UNKNOWN')
        start = time.perf_counter()
        status_code = 500
        trace_value = correlation_id_context.get()
        if trace_value == 'unassigned':
            trace_value = uuid.uuid4().hex
        token = trace_id_context.set(trace_value)

        async def observed_send(message):
            nonlocal status_code
            if message['type'] == 'http.response.start':
                status_code = int(message['status'])
            await send(message)

        try:
            await self.app(scope, receive, observed_send)
        finally:
            duration = time.perf_counter() - start
            metrics.increment('smartwealth_http_requests_total')
            metrics.observe('smartwealth_http_request_duration_seconds', duration)
            if status_code >= 500:
                metrics.increment('smartwealth_http_server_errors_total')
            logger.info(
                'http_request_completed',
                extra={
                    'event': 'http_request_completed',
                    'http_method': method,
                    'http_path': path,
                    'http_status': status_code,
                    'duration_seconds': round(duration, 6),
                },
            )
            trace_id_context.reset(token)


@contextmanager
def bind_run(run_id: str) -> Iterator[None]:
    token = run_id_context.set(run_id)
    try:
        yield
    finally:
        run_id_context.reset(token)


@contextmanager
def bind_provider_attempt(attempt_id: str) -> Iterator[None]:
    token = provider_attempt_context.set(attempt_id)
    try:
        yield
    finally:
        provider_attempt_context.reset(token)


@contextmanager
def trace_span(name: str, **fields: Any) -> Iterator[str]:
    inherited = trace_id_context.get()
    trace_id = inherited if inherited != 'unassigned' else uuid.uuid4().hex
    token = trace_id_context.set(trace_id)
    start = time.perf_counter()
    logger.info('span_started', extra={'event': 'span_started', 'span': name, **fields})
    try:
        yield trace_id
    except Exception as error:
        metrics.increment('smartwealth_span_errors_total')
        logger.error(
            'span_failed',
            extra={
                'event': 'span_failed',
                'span': name,
                'error_class': type(error).__name__,
                **fields,
            },
        )
        raise
    finally:
        duration = time.perf_counter() - start
        metrics.observe('smartwealth_span_duration_seconds', duration)
        logger.info(
            'span_finished',
            extra={
                'event': 'span_finished',
                'span': name,
                'duration_seconds': round(duration, 6),
                **fields,
            },
        )
        trace_id_context.reset(token)
