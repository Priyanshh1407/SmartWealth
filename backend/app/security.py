import re
import time
import uuid
from collections import defaultdict, deque
from contextvars import ContextVar
from threading import Lock
from typing import Any

from fastapi import HTTPException
from starlette.datastructures import MutableHeaders
from starlette.responses import JSONResponse

from backend.app.config import get_settings


REQUEST_ID_PATTERN = re.compile(r'^[A-Za-z0-9._-]{8,128}$')
correlation_id_context: ContextVar[str] = ContextVar(
    'correlation_id',
    default='unassigned',
)



class FixedWindowRateLimiter:
    def __init__(self, limit: int, window_seconds: int = 60):
        self.limit = limit
        self.window_seconds = window_seconds
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def check(self, key: str) -> None:
        now = time.monotonic()
        cutoff = now - self.window_seconds
        with self._lock:
            events = self._events[key]
            while events and events[0] <= cutoff:
                events.popleft()
            if len(events) >= self.limit:
                raise HTTPException(
                    status_code=429,
                    detail='Request rate limit exceeded.',
                    headers={'Retry-After': str(self.window_seconds)},
                )
            events.append(now)


class BodySizeLimitMiddleware:
    def __init__(self, app: Any, max_bytes: int):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get('headers', []))
        content_length = headers.get(b'content-length')
        if content_length:
            try:
                if int(content_length) > self.max_bytes:
                    response = JSONResponse(
                        {'detail': 'Request body is too large.'},
                        status_code=413,
                    )
                    await response(scope, receive, send)
                    return
            except ValueError:
                response = JSONResponse(
                    {'detail': 'Invalid Content-Length header.'},
                    status_code=400,
                )
                await response(scope, receive, send)
                return
        consumed = 0

        async def limited_receive():
            nonlocal consumed
            message = await receive()
            if message['type'] == 'http.request':
                consumed += len(message.get('body', b''))
                if consumed > self.max_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail='Request body is too large.',
                    )
            return message

        try:
            await self.app(scope, limited_receive, send)
        except HTTPException as error:
            response = JSONResponse(
                {'detail': error.detail},
                status_code=error.status_code,
            )
            await response(scope, receive, send)


class RequestSecurityMiddleware:
    def __init__(self, app: Any):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get('headers', []))
        supplied = headers.get(b'x-request-id', b'').decode(
            'ascii',
            errors='ignore',
        )
        correlation_id = (
            supplied
            if REQUEST_ID_PATTERN.fullmatch(supplied)
            else str(uuid.uuid4())
        )
        token = correlation_id_context.set(correlation_id)
        scope.setdefault('state', {})['correlation_id'] = correlation_id

        async def secure_send(message):
            if message['type'] == 'http.response.start':
                response_headers = MutableHeaders(scope=message)
                response_headers['X-Request-ID'] = correlation_id
                response_headers['X-Content-Type-Options'] = 'nosniff'
                response_headers['X-Frame-Options'] = 'DENY'
                response_headers['Referrer-Policy'] = 'no-referrer'
                response_headers['Permissions-Policy'] = (
                    'camera=(), microphone=(), geolocation=()'
                )
                response_headers['Cache-Control'] = 'no-store'
                response_headers['Content-Security-Policy'] = (
                    "default-src 'none'; frame-ancestors 'none'"
                )
                if scope.get('scheme') == 'https':
                    response_headers['Strict-Transport-Security'] = (
                        'max-age=31536000; includeSubDomains'
                    )
            await send(message)

        try:
            await self.app(scope, receive, secure_send)
        finally:
            correlation_id_context.reset(token)


settings = get_settings()
rate_limiter = FixedWindowRateLimiter(settings.requests_per_minute)
