import os
import time
import shutil
import logging
import subprocess
import datetime
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.config import settings
from app.models.download_catalog import DownloadCatalog
from app.models.download_task import DownloadTask
from app.models.user import User

logger = logging.getLogger(__name__)
router = APIRouter(tags=["status"])

PROJECT_ROOT = None
templates = None

_start_time = time.time()


def _get_project_root():
    global PROJECT_ROOT
    if PROJECT_ROOT is None:
        from pathlib import Path
        PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
    return PROJECT_ROOT


def _get_templates():
    global templates
    if templates is None:
        from pathlib import Path
        tdir = _get_project_root() / "templates"
        if tdir.exists():
            templates = Jinja2Templates(directory=str(tdir))
    return templates


@router.get("/status", response_class=HTMLResponse)
async def status_page(request: Request):
    tmpl = _get_templates()
    if not tmpl:
        return HTMLResponse("<h1>No templates</h1>")
    return tmpl.TemplateResponse(request, "status.html", {"page_title": "System Status"})


@router.get("/api/status")
async def system_status(
    db: AsyncSession = Depends(get_db),
):
    disk = shutil.disk_usage(settings.media_root)
    uptime_secs = time.time() - _start_time
    uptime_str = str(datetime.timedelta(seconds=int(uptime_secs)))

    # aria2
    aria2_alive = False
    aria2_proc = None
    try:
        from app.services.downloader import aria2_process
        aria2_proc = aria2_process
        aria2_alive = aria2_process is not None and aria2_process.poll() is None
    except Exception:
        pass

    # Catalog stats
    total_catalog = 0
    entries_with_covers = 0
    movies = 0
    series = 0
    try:
        count_q = select(func.count(DownloadCatalog.id))
        total_catalog = (await db.execute(count_q)).scalar() or 0
        cover_q = select(func.count(DownloadCatalog.id)).where(DownloadCatalog.cover_url != "")
        entries_with_covers = (await db.execute(cover_q)).scalar() or 0
        movies_q = select(func.count(DownloadCatalog.id)).where(DownloadCatalog.title_type == "movie")
        movies = (await db.execute(movies_q)).scalar() or 0
        series_q = select(func.count(DownloadCatalog.id)).where(DownloadCatalog.title_type.in_(["series", "tv_series"]))
        series = (await db.execute(series_q)).scalar() or 0
    except Exception as e:
        logger.warning(f"Catalog stats query failed: {e}")

    # Download stats
    total_downloads = 0
    active_downloads = 0
    completed_downloads = 0
    failed_downloads = 0
    paused_downloads = 0
    interrupted_downloads = 0
    scheduled_downloads = 0
    total_downloaded_bytes = 0
    active_dl_list = []
    try:
        dl_count = select(func.count(DownloadTask.id))
        total_downloads = (await db.execute(dl_count)).scalar() or 0
        active_q = select(func.count(DownloadTask.id)).where(
            DownloadTask.status.in_(["downloading", "active", "waiting", "queued"])
        )
        active_downloads = (await db.execute(active_q)).scalar() or 0
        completed_q = select(func.count(DownloadTask.id)).where(DownloadTask.status == "completed")
        completed_downloads = (await db.execute(completed_q)).scalar() or 0
        failed_q = select(func.count(DownloadTask.id)).where(DownloadTask.status == "error")
        failed_downloads = (await db.execute(failed_q)).scalar() or 0
        paused_q = select(func.count(DownloadTask.id)).where(DownloadTask.status == "paused")
        paused_downloads = (await db.execute(paused_q)).scalar() or 0
        interrupted_q = select(func.count(DownloadTask.id)).where(DownloadTask.status == "interrupted")
        interrupted_downloads = (await db.execute(interrupted_q)).scalar() or 0
        scheduled_q = select(func.count(DownloadTask.id)).where(DownloadTask.status == "queued", DownloadTask.scheduled_at.isnot(None))
        scheduled_downloads = (await db.execute(scheduled_q)).scalar() or 0

        # Count total bytes as sum of completed downloads' total_bytes
        from sqlalchemy import cast as sa_cast, Integer
        bytes_q = select(func.sum(sa_cast(DownloadTask.downloaded_bytes, Integer)))
        total_downloaded_bytes = (await db.execute(bytes_q)).scalar() or 0

        # Active download details
        active_rows = await db.execute(
            select(DownloadTask).where(
                DownloadTask.status.in_(["downloading", "active"])
            ).order_by(DownloadTask.created_at.desc()).limit(20)
        )
        for t in active_rows.scalars().all():
            active_dl_list.append({
                "id": t.id,
                "title": t.title,
                "file_name": t.file_name,
                "progress": t.progress_pct,
                "speed": t.speed,
                "total_bytes": t.total_bytes,
                "downloaded_bytes": t.downloaded_bytes,
                "status": t.status,
            })
    except Exception as e:
        logger.warning(f"Download stats query failed: {e}")

    # Scraper health
    scraper_status = []
    try:
        from app.services.scraper_registry import get_registry as get_scr_registry, get_health as get_scr_health
        for name, scraper in get_scr_registry().items():
            healthy = True
            err = ""
            try:
                from app.services.base_scraper import BaseScraper
                if not isinstance(scraper, BaseScraper):
                    healthy = False
                    err = "not a BaseScraper instance"
            except Exception as e:
                healthy = False
                err = str(e)
            health_info = get_scr_health().get(name, {})
            entry = {
                "name": name,
                "enabled": scraper.enabled,
                "healthy": healthy,
                "error": err,
                "class": type(scraper).__name__,
                "consecutive_fails": health_info.get("consecutive_fails", 0),
                "total_searches": health_info.get("total_searches", 0),
                "last_error": health_info.get("last_error"),
                "last_success_ts": health_info.get("last_success_ts"),
                "last_error_ts": health_info.get("last_error_ts"),
                "in_cooldown": health_info.get("cooldown_until", 0) > __import__("time").time(),
            }
            # Add archive cache info for donyayeserial
            if name == "donyayeserial":
                try:
                    from app.services.scraper import get_archive_cache_info
                    entry["archive_cache"] = get_archive_cache_info()
                except Exception:
                    pass
            scraper_status.append(entry)
    except Exception as e:
        logger.warning(f"Scraper health check failed: {e}")

    # User count
    user_count = 0
    try:
        user_q = select(func.count(User.id))
        user_count = (await db.execute(user_q)).scalar() or 0
    except Exception:
        pass

    # API services status
    from app.services import tmdb, omdb, fanart, tvdb, opensubtitles
    api_services = {
        "tmdb": {
            "configured": tmdb.is_configured(),
            "reachable": tmdb.is_configured() and not tmdb._network_bad and not tmdb._auth_bad,
        },
        "omdb": {"configured": omdb.is_configured(), "reachable": omdb.is_configured()},
        "fanart": {"configured": fanart.is_configured(), "reachable": fanart.is_configured()},
        "tvdb": {"configured": tvdb.is_configured(), "reachable": tvdb.is_configured()},
        "opensubtitles": {"configured": opensubtitles.is_configured(), "reachable": opensubtitles.is_configured()},
    }

    # Local AI status
    ai_model_path = "/mnt/hdd/models/qwen2.5-3b-instruct-q4_k_m.gguf"
    ai_healthy = False
    try:
        import httpx
        h = httpx.get("http://127.0.0.1:8081/health", timeout=3)
        ai_healthy = h.status_code == 200
    except Exception:
        pass
    ai_categorized = 0
    try:
        from app.models.file_category import FileCategory
        ai_count_q = select(func.count(FileCategory.file_path))
        ai_categorized = (await db.execute(ai_count_q)).scalar() or 0
    except Exception:
        pass
    local_ai = {
        "healthy": ai_healthy,
        "model": os.path.basename(ai_model_path) if os.path.exists(ai_model_path) else "not_found",
        "categorized": ai_categorized,
        "port": 8081,
    }

    return {
        "success": True,
        "server": {
            "uptime": uptime_str,
            "uptime_seconds": int(uptime_secs),
            "host": settings.host,
            "port": settings.port,
            "env": settings.env,
            "debug": settings.debug,
        },
        "disk": {
            "total": disk.total,
            "used": disk.used,
            "free": disk.free,
            "usage_pct": round(disk.used / disk.total * 100, 1),
            "media_root": settings.media_root,
            "media_root_exists": os.path.exists(settings.media_root),
        },
        "aria2": {
            "alive": aria2_alive,
            "process": aria2_proc is not None,
        },
        "catalog": {
            "total": total_catalog,
            "movies": movies,
            "series": series,
            "with_covers": entries_with_covers,
            "coverage_pct": round(entries_with_covers / total_catalog * 100, 1) if total_catalog > 0 else 0,
        },
        "downloads": {
            "total": total_downloads,
            "active": active_downloads,
            "completed": completed_downloads,
            "failed": failed_downloads,
            "paused": paused_downloads,
            "interrupted": interrupted_downloads,
            "scheduled": scheduled_downloads,
            "total_bytes_downloaded": total_downloaded_bytes,
            "active_list": active_dl_list,
        },
        "scrapers": scraper_status,
        "users": user_count,
        "apis": api_services,
        "local_ai": local_ai,
    }
