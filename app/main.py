import os
import json
import logging
import sys
import time
import datetime
from pathlib import Path
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings
from app.database import init_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
    ],
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("apscheduler").setLevel(logging.WARNING)
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = PROJECT_ROOT / "static"
TEMPLATES_DIR = PROJECT_ROOT / "templates"

from functools import lru_cache
from fastapi.templating import Jinja2Templates


@lru_cache(maxsize=1)
def _get_templates():
    return Jinja2Templates(directory=str(TEMPLATES_DIR))


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("=" * 60)
    logger.info(f"OpenPlex Server Starting...")
    logger.info(f"Root: {settings.media_root}")
    logger.info(f"Server: http://{settings.host}:{settings.port}")
    logger.info(f"Env: {settings.env}")
    logger.info("=" * 60)

    await init_db()

    # Mark stale downloads
    from app.database import async_session
    from app.models.download_task import DownloadTask
    try:
        async with async_session() as db:
            from sqlalchemy import update
            stmt = (
                update(DownloadTask)
                .where(DownloadTask.status.in_(["downloading", "active", "queued", "paused", "waiting"]))
                .values(status="interrupted", error_message="Server restarted — old downloads are no longer tracked")
            )
            await db.execute(stmt)
            await db.commit()
            logger.info("Stale downloads marked as interrupted")
    except Exception as e:
        logger.warning(f"Could not clean stale downloads: {e}")

    from app.services.downloader import start_aria2, start_aria2_watchdog
    start_aria2()
    start_aria2_watchdog()

    # Background cover enrichment
    _enrich_lock = False
    async def background_enrich(batch: int = 50):
        nonlocal _enrich_lock
        if _enrich_lock: return
        _enrich_lock = True
        try:
            from app.services.catalog_enricher import enrich_covers_only
            from app.database import async_session
            async with async_session() as db:
                done = await enrich_covers_only(db, limit=batch)
                if done:
                    logger.info(f"Background enrichment: {done} covers added")
        except Exception as e:
            logger.warning(f"Background enrichment failed: {e}")
        finally:
            _enrich_lock = False

    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    enrich_scheduler = AsyncIOScheduler()
    enrich_scheduler.add_job(background_enrich, "interval", seconds=300, max_instances=1, coalesce=True, kwargs={"batch": 200})
    enrich_scheduler.start()
    logger.info("Background cover enrichment scheduled every 300s")

    async def initial_enrich():
        await background_enrich(batch=2000)
    import asyncio
    asyncio.create_task(initial_enrich())

    # Scheduled cleanup: strip ' start_year' artifact from catalog titles (every hour)
    start_year_scheduler = AsyncIOScheduler()
    async def fix_start_year():
        try:
            from app.services.catalog_enricher import fix_start_year_artifacts
            from app.database import async_session
            async with async_session() as db:
                done = await fix_start_year_artifacts(db)
                if done:
                    logger.info(f"Fixed {done} titles with start_year artifact")
        except Exception as e:
            logger.warning(f"start_year fix failed: {e}")
    start_year_scheduler.add_job(fix_start_year, "interval", minutes=60, max_instances=1, coalesce=True)
    start_year_scheduler.start()
    # Run once immediately
    asyncio.create_task(fix_start_year())

    # Background AI file categorization (hybrid — runs every 15 min, 100 files per batch)
    _cat_lock = False
    async def background_categorize():
        nonlocal _cat_lock
        if _cat_lock: return
        _cat_lock = True
        try:
            from app.services.file_categorizer import batch_categorize_files
            from app.database import async_session
            async with async_session() as db:
                done = await batch_categorize_files(db, settings.media_root, limit=100)
                if done:
                    logger.info(f"Background categorization: {done} files categorized")
        except Exception as e:
            logger.warning(f"Background categorization failed: {e}")
        finally:
            _cat_lock = False

    cat_scheduler = AsyncIOScheduler()
    cat_scheduler.add_job(background_categorize, "interval", minutes=15, max_instances=1, coalesce=True)
    cat_scheduler.start()
    logger.info("Background file categorization scheduled every 15 min")

    # Run initial categorization batch
    async def initial_cat():
        await background_categorize()
    asyncio.create_task(initial_cat())

    # Background metadata enrichment — fills overview/genres/cast/backdrops
    # for catalog rows using TMDB, OMDb, TVDb, Fanart.tv.
    _tmdb_lock = False
    async def background_tmdb_enrich(batch: int = 30):
        nonlocal _tmdb_lock
        if _tmdb_lock: return
        _tmdb_lock = True
        try:
            from app.services.tmdb_enricher import enrich_batch
            from app.services import tmdb, omdb, tvdb, fanart
            sources = [s for s, fn in [("TMDB", tmdb), ("OMDb", omdb), ("TVDb", tvdb), ("Fanart", fanart)] if fn.is_configured()]
            if not sources:
                return
            async with async_session() as db:
                done = await enrich_batch(db, limit=batch)
                if done:
                    logger.info(f"Metadata enrichment: {done} entries updated via {'+'.join(sources)}")
        except Exception as e:
            logger.warning(f"Background enrichment failed: {e}")
        finally:
            _tmdb_lock = False

    from app.services import tmdb, omdb, tvdb, fanart
    sources = [s for s, fn in [("TMDB", tmdb), ("OMDb", omdb), ("TVDb", tvdb), ("Fanart", fanart)] if fn.is_configured()]
    if sources:
        tmdb_scheduler = AsyncIOScheduler()
        tmdb_scheduler.add_job(background_tmdb_enrich, "interval", minutes=30, max_instances=1, coalesce=True, kwargs={"batch": 50})
        tmdb_scheduler.start()
        logger.info(f"Metadata background enrichment scheduled every 30 min ({'+'.join(sources)})")
        # Run initial enrichment via create_task in a try/except wrapper
        async def initial_tmdb_wrapper():
            try:
                await background_tmdb_enrich(batch=200)
            except Exception as e:
                logger.warning(f"Initial TMDB enrichment failed: {e}")
        asyncio.create_task(initial_tmdb_wrapper())
    else:
        logger.info("No metadata API keys configured — enrichment disabled")

    # Background scheduler for deferred downloads
    async def check_scheduled_downloads():
        try:
            from app.database import async_session
            from app.models.download_task import DownloadTask
            from app.services.downloader import add_download as add_dl
            from sqlalchemy import select
            async with async_session() as db:
                now = datetime.datetime.now()
                result = await db.execute(
                    select(DownloadTask).where(
                        DownloadTask.status == "queued",
                        DownloadTask.scheduled_at.isnot(None),
                        DownloadTask.scheduled_at <= now,
                    )
                )
                tasks = result.scalars().all()
                for t in tasks:
                    gid = await add_dl(t.url, t.dest_path, t.file_name)
                    if gid:
                        t.aria2_gid = gid
                        t.status = "downloading"
                        t.scheduled_at = None
                        logger.info(f"Scheduled download started: {t.title}")
                await db.commit()
        except Exception as e:
            logger.warning(f"Scheduled download check failed: {e}")

    sched_dl_scheduler = AsyncIOScheduler()
    sched_dl_scheduler.add_job(check_scheduled_downloads, "interval", seconds=30, max_instances=1, coalesce=True)
    sched_dl_scheduler.start()
    logger.info("Scheduled download checker started (every 30s)")

    # Catalog auto-refresh
    scheduler = None
    if settings.catalog_auto_refresh:
        from app.services.catalog_updater import update_catalog
        from app.database import async_session
        async def refresh_job():
            try:
                async with async_session() as db:
                    await update_catalog(db)
            except Exception as e:
                logger.warning(f"Scheduled catalog refresh failed: {e}")
        scheduler = AsyncIOScheduler()
        scheduler.add_job(refresh_job, "interval", hours=settings.catalog_refresh_interval_hours)
        scheduler.start()
        logger.info(f"Catalog auto-refresh scheduled every {settings.catalog_refresh_interval_hours}h")
        try:
            async with async_session() as db:
                await update_catalog(db)
        except Exception as e:
            logger.warning(f"Initial catalog refresh failed: {e}")

    # Start idle watcher for local AI (auto-stop after 5 min idle)
    if settings.local_ai_auto_start:
        from app.services.local_ai import start_idle_watcher
        start_idle_watcher()
        logger.info("Local AI idle watcher started (auto_start=True)")
    else:
        logger.info("Local AI auto_start=False — will only start on demand")

    yield

    if scheduler: scheduler.shutdown(wait=False)
    enrich_scheduler.shutdown(wait=False)
    sched_dl_scheduler.shutdown(wait=False)
    cat_scheduler.shutdown(wait=False)
    start_year_scheduler.shutdown(wait=False)
    from app.services.downloader import stop_aria2
    stop_aria2()
    from app.services.scraper_registry import close_all as close_scrapers
    await close_scrapers()
    from app.routers.chat import close_ai_clients
    await close_ai_clients()
    logger.info("Server stopped")


app = FastAPI(title="OpenPlex", version="2.0.0", lifespan=lifespan)

app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.add_middleware(GZipMiddleware, minimum_size=1000)

from app.services.rate_limiter import RateLimitMiddleware
app.add_middleware(RateLimitMiddleware)


# ── Request Logging Middleware ────────────────────────────
_REQUEST_SLOW = 1.0  # log slow requests (>1s) at WARNING level

@app.on_event("startup")
async def _log_routes():
    """Log all registered routes at startup."""
    routes_info = []
    for route in app.routes:
        if hasattr(route, "methods") and hasattr(route, "path"):
            for method in route.methods:
                if method in ("GET", "POST", "PUT", "DELETE", "PATCH"):
                    routes_info.append(f"  {method:7s} {route.path}")
    logger.info("Registered routes:")
    for r in sorted(routes_info):
        logger.info(r)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    duration = time.time() - start
    client = request.client.host if request.client else "unknown"
    level = logging.WARNING if duration > _REQUEST_SLOW else logging.INFO
    logger.log(
        level,
        "%s %s %s [%s] %.3fs",
        request.method,
        request.url.path,
        response.status_code,
        client,
        duration,
    )
    response.headers["X-Response-Time-MS"] = str(round(duration * 1000, 1))
    return response


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Catch-all handler for unhandled exceptions — returns JSON instead of HTML."""
    logger.error("Unhandled exception on %s %s: %s", request.method, request.url.path, exc, exc_info=True)
    from fastapi.responses import JSONResponse
    return JSONResponse(
        status_code=500,
        content={"success": False, "error": "Internal server error", "detail": str(exc)},
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Structured JSON responses for HTTP errors."""
    from fastapi.responses import JSONResponse
    return JSONResponse(
        status_code=exc.status_code,
        content={"success": False, "error": exc.detail},
    )

@app.get("/favicon.ico")
async def favicon():
    return FileResponse(str(STATIC_DIR / "favicon.svg"), media_type="image/svg+xml")

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

from app.services.cache import response_cache

from app.routers import auth, browse, media, history, downloads, catalog, status as status_router
from app.routers import health as health_router, ai as ai_router, chat as chat_router, settings as settings_router
app.include_router(auth.router)
app.include_router(browse.router)
app.include_router(media.router)
app.include_router(history.router)
app.include_router(downloads.router)
app.include_router(catalog.router)
app.include_router(status_router.router)
app.include_router(health_router.router)
app.include_router(ai_router.router)
app.include_router(chat_router.router)
app.include_router(settings_router.router)

try:
    from app.routers import library as library_router
    app.include_router(library_router.router)
except ImportError:
    pass

try:
    from app.routers import metrics as metrics_router
    app.include_router(metrics_router.router)
except ImportError:
    pass

# ── Template Routes ───────────────────────────────────────

@app.get("/")
async def index(request: Request):
    logger.debug("GET /")
    return _get_templates().TemplateResponse(request, "index.html")

@app.get("/login")
async def login_page(request: Request):
    logger.debug("GET /login")
    return _get_templates().TemplateResponse(request, "login.html")

@app.get("/register")
async def register_page(request: Request):
    logger.debug("GET /register")
    return _get_templates().TemplateResponse(request, "register.html")

@app.get("/library")
async def library_page(request: Request):
    logger.debug("GET /library")
    return _get_templates().TemplateResponse(request, "library.html")

@app.get("/player")
async def player_page(request: Request):
    logger.debug("GET /player")
    from starlette.responses import RedirectResponse
    qs = str(request.query_params)
    redirect = f"/library"
    if qs:
        redirect += f"?{qs}"
    return RedirectResponse(url=redirect)

@app.get("/downloads")
async def downloads_page(request: Request):
    logger.debug("GET /downloads")
    return _get_templates().TemplateResponse(request, "downloads.html")

@app.get("/status")
async def status_page(request: Request):
    logger.debug("GET /status")
    return _get_templates().TemplateResponse(request, "status.html")

@app.get("/upload")
async def upload_page(request: Request):
    logger.debug("GET /upload")
    return _get_templates().TemplateResponse(request, "upload.html")

@app.get("/chat")
async def chat_page(request: Request):
    logger.debug("GET /chat")
    return _get_templates().TemplateResponse(request, "chat.html")

@app.get("/profile")
async def profile_page(request: Request):
    logger.debug("GET /profile")
    return _get_templates().TemplateResponse(request, "profile.html")

@app.get("/health")
async def health_page(request: Request):
    logger.debug("GET /health")
    return _get_templates().TemplateResponse(request, "health.html")

# ── API Health ────────────────────────────────────────────

@app.get("/api/health")
async def health_check():
    import shutil
    disk = shutil.disk_usage(settings.media_root)
    aria2_alive = False
    try:
        from app.services.downloader import aria2_process
        aria2_alive = aria2_process is not None and aria2_process.poll() is None
    except Exception: pass
    return {
        "status": "ok",
        "media_root": settings.media_root,
        "media_root_exists": os.path.exists(settings.media_root),
        "disk_total": disk.total,
        "disk_used": disk.used,
        "disk_free": disk.free,
        "disk_usage_pct": round(disk.used / disk.total * 100, 1) if disk.total > 0 else 0,
        "aria2_alive": aria2_alive,
    }

@app.get("/api/ai-health")
async def ai_health():
    healthy = False
    try:
        import httpx
        async with httpx.AsyncClient(timeout=3) as c:
            r = await c.get("http://127.0.0.1:8081/health")
            healthy = r.status_code == 200
    except Exception:
        pass
    categorized = 0
    try:
        from app.database import async_session
        from app.models.file_category import FileCategory
        from sqlalchemy import select, func
        async with async_session() as db:
            categorized = (await db.execute(select(func.count(FileCategory.file_path)))).scalar() or 0
    except Exception:
        pass
    return {"healthy": healthy, "categorized": categorized}


@app.on_event("shutdown")
async def shutdown_clear():
    from app.services.cache import response_cache
    response_cache.clear()
    from app.routers.chat import close_chat_client
    await close_chat_client()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=settings.debug)
