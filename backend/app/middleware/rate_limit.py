import time
from collections import defaultdict, deque
from typing import Deque, Dict

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

RATE_LIMITED_PREFIXES = (
    "/api/auth/login",
    "/api/auth/register",
    "/api/auth/otp/send",
    "/api/auth/recover-with-code",
    "/api/auth/forgot-password-email",
    "/api/reports",
)


class SecurityAndRateLimitMiddleware(BaseHTTPMiddleware):
    """Add defensive security headers and sliding-window rate limiting on sensitive endpoints."""

    def __init__(self, app, max_requests_per_minute: int = 60) -> None:
        super().__init__(app)
        self.max_requests_per_minute = max_requests_per_minute
        self._hits: Dict[str, Deque[float]] = defaultdict(deque)

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if request.method == "POST" and any(path.startswith(prefix) for prefix in RATE_LIMITED_PREFIXES):
            client_ip = request.client.host if request.client else "unknown"
            bucket_key = f"{client_ip}:{path}"
            now = time.monotonic()
            window_start = now - 60.0
            dq = self._hits[bucket_key]
            while dq and dq[0] < window_start:
                dq.popleft()
            if len(dq) >= self.max_requests_per_minute:
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Too many requests. Please wait a minute before trying again."},
                )
            dq.append(now)

        response = await call_next(request)
        if path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        return response
