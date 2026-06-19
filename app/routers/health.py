"""Detailed health check endpoint with per-component breakdown."""

import os
import time
import shutil
import platform
import logging

from fastapi import APIRouter
from app.config import settings
from app.database import async_session
from app.services.downloader import rpc_call as aria2_rpc_call

logger = logging.getLogger(__name__)
router = APIRouter(tags=["health"])


@router.get("/api/health/detailed")
async def detailed_health():
    logger.debug("Health check requested")
    checks = {}

    # Database check
    db_ok = False
    db_latency = None
    try:
        t0 = time.monotonic()
        async with async_session() as session:
            from sqlalchemy import text
            await session.execute(text("SELECT 1"))
        db_latency = round((time.monotonic() - t0) * 1000, 1)
        db_ok = True
    except Exception as e:
        logger.warning(f"Health DB check failed: {e}")

    checks["database"] = {
        "status": "ok" if db_ok else "error",
        "connected": db_ok,
        "query_time_ms": db_latency,
    }

    # aria2 RPC check
    aria2_alive = False
    aria2_latency = None
    aria2_version = None
    try:
        t0 = time.monotonic()
        version_info = await aria2_rpc_call("aria2.getVersion")
        aria2_latency = round((time.monotonic() - t0) * 1000, 1)
        if version_info and "result" in version_info:
            aria2_alive = True
            aria2_version = version_info["result"].get("version", "unknown")
    except Exception as e:
        logger.warning(f"Health aria2 check failed: {e}")

    checks["aria2"] = {
        "status": "ok" if aria2_alive else "error",
        "alive": aria2_alive,
        "latency_ms": aria2_latency,
        "version": aria2_version,
    }

    # Disk check
    disk_ok = False
    try:
        du = shutil.disk_usage(settings.media_root)
        disk_ok = True
    except Exception:
        du = None

    if du:
        usage_pct = round(du.used / du.total * 100, 1) if du.total > 0 else 0
        checks["disk"] = {
            "status": "ok" if usage_pct < 95 else "warning",
            "total_bytes": du.total,
            "used_bytes": du.used,
            "free_bytes": du.free,
            "usage_percent": usage_pct,
        }
    else:
        checks["disk"] = {"status": "error", "detail": "Could not query disk usage"}

    # Media root check
    media_root_path = str(settings.media_root)
    media_root_exists = os.path.exists(settings.media_root)
    media_root_writable = os.access(settings.media_root, os.W_OK) if media_root_exists else False
    checks["media_root"] = {
        "status": "ok" if media_root_exists and media_root_writable else "error",
        "path": media_root_path,
        "exists": media_root_exists,
        "writable": media_root_writable,
    }

    # Scraper health — test each by doing a brief search
    scraper_sources = []
    try:
        from app.services.scraper_registry import get_registry
        scrapers = get_registry()
        for name, sc in scrapers.items():
            t0 = time.monotonic()
            try:
                import asyncio
                await asyncio.wait_for(sc.search("a", page=1), timeout=5)
                latency = round((time.monotonic() - t0) * 1000, 1)
                scraper_sources.append({"name": name, "reachable": True, "latency_ms": latency})
            except Exception:
                scraper_sources.append({"name": name, "reachable": False, "latency_ms": None})
    except Exception as e:
        logger.warning(f"Health scraper check failed: {e}")

    checks["scrapers"] = {
        "status": "ok",
        "sources": scraper_sources,
    }

    # System info
    import datetime
    checks["uptime"] = {
        "status": "ok",
        "server_uptime": datetime.datetime.now().isoformat(),
        "python_version": platform.python_version(),
        "os": f"{platform.system()} {platform.release()}",
    }

    overall = "ok" if all(
        c.get("status") == "ok" for c in checks.values()
    ) else "degraded"

    return {
        "status": overall,
        "checks": checks,
        "timestamp": time.time(),
    }
