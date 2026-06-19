"""Simple in-memory rate limiter middleware.

Limits requests per IP using a sliding window counter.
Suitable for LAN use; for production internet exposure, use nginx rate limiting.
"""
import time
import logging
from collections import defaultdict
from typing import Dict, Tuple

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)

# Default limits: (requests_per_minute, burst_per_second)
DEFAULT_LIMITS: Dict[str, Tuple[int, int]] = {
    "/api/auth/login": (10, 2),
    "/api/auth/register": (5, 1),
    "/api/chat": (20, 4),
    "/api/chat/stream": (20, 4),
}
DEFAULT_LIMIT = (120, 20)  # 120 req/min, 20 burst for all other endpoints


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Per-IP sliding window rate limiter."""

    def __init__(self, app, default_limit=DEFAULT_LIMIT, path_limits=None):
        super().__init__(app)
        self.default_limit = default_limit
        self.path_limits = path_limits or DEFAULT_LIMITS
        # {ip: {path: [(timestamp, ...)]}}
        self._windows: Dict[str, Dict[str, list]] = defaultdict(lambda: defaultdict(list))
        self._cleanup_interval = 60
        self._last_cleanup = time.time()

    def _get_limit(self, path: str) -> Tuple[int, int]:
        """Return (per_minute, per_second) limit for a path."""
        for pattern, limit in self.path_limits.items():
            if path.startswith(pattern):
                return limit
        return self.default_limit

    def _cleanup(self):
        """Evict old entries periodically."""
        now = time.time()
        if now - self._last_cleanup < self._cleanup_interval:
            return
        self._last_cleanup = now
        cutoff = now - 120  # keep 2 minutes of history
        stale_ips = []
        for ip, paths in self._windows.items():
            stale_paths = []
            for path, timestamps in paths.items():
                self._windows[ip][path] = [t for t in timestamps if t > cutoff]
                if not self._windows[ip][path]:
                    stale_paths.append(path)
            for p in stale_paths:
                del self._windows[ip][p]
            if not self._windows[ip]:
                stale_ips.append(ip)
        for ip in stale_ips:
            del self._windows[ip]

    async def dispatch(self, request: Request, call_next):
        # Skip rate limiting for static files and health checks
        path = request.url.path
        if path.startswith("/static") or path == "/favicon.ico" or path == "/api/health":
            return await call_next(request)

        ip = request.client.host if request.client else "unknown"
        per_minute, per_second = self._get_limit(path)

        self._cleanup()

        now = time.time()
        window = self._windows[ip][path]

        # Check burst limit (per second)
        recent_burst = [t for t in window if now - t < 1.0]
        if len(recent_burst) >= per_second:
            logger.warning("Rate limit burst hit: ip=%s path=%s", ip, path)
            return Response(
                content='{"success": false, "error": "Rate limit exceeded (burst)"}',
                status_code=429,
                media_type="application/json",
                headers={"Retry-After": "1"},
            )

        # Check minute limit
        recent_minute = [t for t in window if now - t < 60.0]
        if len(recent_minute) >= per_minute:
            logger.warning("Rate limit exceeded: ip=%s path=%s (%d/%d)", ip, path, len(recent_minute), per_minute)
            return Response(
                content='{"success": false, "error": "Rate limit exceeded"}',
                status_code=429,
                media_type="application/json",
                headers={"Retry-After": "60"},
            )

        window.append(now)
        return await call_next(request)
