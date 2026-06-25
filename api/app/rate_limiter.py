from __future__ import annotations

from typing import Any, Callable

from fastapi import Request
from fastapi.responses import JSONResponse

from api.app.config import settings

try:
    from slowapi import Limiter as _SlowapiLimiter
    from slowapi import _rate_limit_exceeded_handler as rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded
    from slowapi.middleware import SlowAPIMiddleware
    from slowapi.util import get_remote_address

    RATE_LIMITING_AVAILABLE = True

    def _client_identifier(request: Request) -> str:
        if settings.trust_proxy_headers:
            forwarded_for = request.headers.get("x-forwarded-for", "").strip()
            if forwarded_for:
                return forwarded_for.split(",", 1)[0].strip()
            real_ip = request.headers.get("x-real-ip", "").strip()
            if real_ip:
                return real_ip
        return get_remote_address(request)

    limiter = _SlowapiLimiter(key_func=_client_identifier, headers_enabled=True)
except ImportError:  # pragma: no cover - fallback for local/dev environments without slowapi installed
    RATE_LIMITING_AVAILABLE = False

    class RateLimitExceeded(Exception):
        pass

    class SlowAPIMiddleware:  # type: ignore[override]
        def __init__(self, app: Any, **_: Any) -> None:
            self.app = app

        async def __call__(self, scope: dict, receive: Callable[..., Any], send: Callable[..., Any]) -> None:
            await self.app(scope, receive, send)

    def rate_limit_exceeded_handler(request: Request, exc: Exception) -> JSONResponse:
        del request, exc
        return JSONResponse(status_code=429, content={"detail": "Rate limit exceeded"})

    class _NoOpLimiter:
        def limit(self, _value: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
            def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
                return func

            return decorator

    limiter = _NoOpLimiter()
