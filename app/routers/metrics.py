"""Prometheus metrics endpoint for monitoring."""

import logging
from fastapi import APIRouter
from starlette.responses import Response

logger = logging.getLogger(__name__)
router = APIRouter(tags=["metrics"])

# Simple in-memory counters
METRICS = {
    "http_requests_total": 0,
    "download_bytes_total": 0,
    "transcode_seconds_total": 0.0,
}


def inc_counter(name: str, value: int = 1):
    METRICS[name] = METRICS.get(name, 0) + value


def add_counter(name: str, value: float):
    METRICS[name] = METRICS.get(name, 0) + value


@router.get("/metrics", response_class=Response)
async def metrics():
    lines = [
        "# HELP http_requests_total Total HTTP requests",
        "# TYPE http_requests_total counter",
        f'http_requests_total {METRICS.get("http_requests_total", 0)}',
        "",
        "# HELP download_bytes_total Total bytes downloaded via aria2",
        "# TYPE download_bytes_total counter",
        f'download_bytes_total {METRICS.get("download_bytes_total", 0)}',
        "",
        "# HELP transcode_seconds_total Total ffmpeg transcode time in seconds",
        "# TYPE transcode_seconds_total counter",
        f'transcode_seconds_total {METRICS.get("transcode_seconds_total", 0)}',
        "",
    ]
    return "\n".join(lines)
