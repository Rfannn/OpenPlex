import json
import os
import subprocess
import logging
import urllib.parse
import datetime
import asyncio
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Body
from pydantic import BaseModel
from fastapi.responses import FileResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm.exc import StaleDataError

from app.database import get_db, async_session
from app.config import settings
from app.models.download_catalog import DownloadCatalog
from app.models.download_task import DownloadTask
from app.models.user import User
from app.dependencies import get_current_user, require_admin
from app.services.scraper import fetch_season_page, parse_apache_listing
from app.services.downloader import add_download, get_progress, cancel_download, pause_download, resume_download, rpc_call

logger = logging.getLogger(__name__)
router = APIRouter(tags=["downloads"])

_dl_settings = {"max_concurrent": 3}

VIDEO_EXTS = {".mkv", ".mp4", ".avi", ".mov", ".webm", ".m4v", ".flv", ".wmv", ".ogv"}


# ============ SHARED HELPERS ============

async def _sync_task_progress(t: DownloadTask) -> None:
    """Poll aria2 for live progress and update a DownloadTask in-place.

    Also handles auto-retry on transient errors (up to 3 retries).
    """
    if not t.aria2_gid or t.status in ("completed", "error", "interrupted"):
        return

    progress = await get_progress(t.aria2_gid)
    if "result" in progress:
        p = progress["result"]
        st = p.get("status", t.status)
        if st != t.status:
            t.status = st
        t.total_bytes = p.get("totalLength", "0")
        t.downloaded_bytes = p.get("completedLength", "0")
        t.speed = p.get("downloadSpeed", "0")
        total = int(p.get("totalLength", "0"))
        downloaded = int(p.get("completedLength", "0"))
        t.progress_pct = (downloaded / total * 100) if total > 0 else 0
        if t.status == "complete":
            t.status = "completed"
            t.completed_at = datetime.datetime.now()
            t.retry_count = 0
    elif "error" in progress:
        t.status = "error"
        err = progress["error"]
        if isinstance(err, dict):
            code = err.get("code", 0)
            msg = err.get("message", "")
            if code == 1:
                t.error_message = "GID not found — download session expired"
            else:
                t.error_message = msg or f"aria2 error (code {code})"
        else:
            t.error_message = str(err)

    # Auto-retry on transient failures
    if t.status == "error" and t.retry_count < 3 and t.url:
        t.retry_count += 1
        new_gid = await add_download(t.url, t.dest_path, t.file_name)
        if new_gid:
            t.aria2_gid = new_gid
            t.status = "downloading"
            t.error_message = ""
            t.progress_pct = 0.0
            t.total_bytes = "0"
            t.downloaded_bytes = "0"
            t.speed = ""
            logger.info(f"Auto-retry #{t.retry_count} for task {t.id}: {t.title}")


def _task_to_dict(t: DownloadTask, cover_map: dict) -> dict:
    """Serialize a DownloadTask to a JSON-friendly dict."""
    return {
        "id": t.id, "title": t.title, "file_name": t.file_name,
        "status": t.status, "progress_pct": t.progress_pct,
        "total_bytes": t.total_bytes, "downloaded_bytes": t.downloaded_bytes,
        "speed": t.speed, "quality_label": t.quality_label,
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "error_message": t.error_message,
        "cover_url": cover_map.get(t.id, {}).get("cover_url", ""),
        "imdb_code": cover_map.get(t.id, {}).get("imdb_code", ""),
        "dest_path": t.dest_path,
        "scheduled_at": t.scheduled_at.isoformat() if t.scheduled_at else None,
        "speed_limit": t.speed_limit,
        "retry_count": t.retry_count,
    }


async def set_speed_limit_rpc(gid: str, speed: str):
    try:
        speed_int = int(speed)
        if speed_int <= 0:
            speed_int = 0
        await rpc_call("aria2.changeOption", [gid, {"max-download-limit": str(speed_int)}])
    except (ValueError, Exception) as e:
        logger.warning(f"Failed to set speed limit for {gid}: {e}")


def _ensure_trailing_slash(url: str) -> str:
    return url if url.endswith("/") else url + "/"


def looks_like_media_url(url: str) -> bool:
    _, ext = os.path.splitext(urllib.parse.urlparse(url).path)
    return ext.lower() in VIDEO_EXTS


# ============ DOWNLOAD SETTINGS ============

@router.get("/api/downloads/settings")
async def get_dl_settings(user: User = Depends(get_current_user)):
    logger.debug("Get download settings: user=%s", user.username)
    return {"success": True, **_dl_settings}


@router.put("/api/downloads/settings")
async def update_dl_settings(
    max_concurrent: int = Query(3, ge=1, le=10),
    user: User = Depends(require_admin),
):
    logger.info("Update download settings: max_concurrent=%d user=%s", max_concurrent, user.username)
    _dl_settings["max_concurrent"] = max_concurrent
    return {"success": True, **_dl_settings}


# ============ QUEUE DOWNLOAD (shared helper) ============

async def _queue_download(
    db: AsyncSession,
    user: User,
    url: str,
    dest_dir: str,
    title: str,
    quality_label: str,
    catalog_id: Optional[int],
    file_name: str = "",
    scheduled_at: Optional[str] = None,
    speed_limit: str = "",
):
    from app.config import settings as s
    media_root = os.path.normpath(s.media_root)
    norm_dest = os.path.normpath(dest_dir)
    if not norm_dest.startswith(media_root):
        logger.error(f"Blocked download outside media_root: {dest_dir}")
        return None
    has_space, free = s.check_disk_space(dest_dir)
    if not has_space:
        logger.error(f"Disk space too low ({free} bytes free) — download blocked")
        return None
    os.makedirs(dest_dir, exist_ok=True)
    parsed_scheduled = None
    if scheduled_at:
        try:
            parsed_scheduled = datetime.datetime.fromisoformat(scheduled_at)
        except ValueError:
            pass
    is_scheduled = parsed_scheduled is not None and parsed_scheduled > datetime.datetime.now()
    aria2_gid = None
    if not is_scheduled:
        aria2_gid = await add_download(url, dest_dir, file_name)
    if not aria2_gid and not is_scheduled:
        logger.error(f"aria2 failed for {url}")
        return None
    task = DownloadTask(
        user_id=user.id,
        catalog_id=catalog_id,
        title=title,
        url=url,
        quality_label=quality_label,
        dest_path=dest_dir,
        file_name=file_name or os.path.basename(url),
        status="queued" if is_scheduled or not aria2_gid else "downloading",
        aria2_gid=aria2_gid or "",
        scheduled_at=parsed_scheduled,
        speed_limit=speed_limit if speed_limit else "",
    )
    db.add(task)
    if aria2_gid and speed_limit:
        await set_speed_limit_rpc(aria2_gid, speed_limit)
    return task


# ============ CREATE DOWNLOAD ============

@router.post("/api/downloads")
async def create_download(
    catalog_id: int = Query(0),
    url: str = Query(""),
    quality_label: str = Query(""),
    is_season: bool = Query(False),
    season_name: str = Query(""),
    scheduled_at: str = Query(""),
    speed_limit: str = Query(""),
    title: str = Query(""),
    year: str = Query(""),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    logger.info("Create download: url=%s title=%s quality=%s user=%s", url[:80], title, quality_label, user.username)
    if not url:
        logger.warning("Create download - URL required: user=%s", user.username)
        raise HTTPException(status_code=400, detail="URL required")
    title_out = title or "Unknown"
    year_out = year
    dest_dir = os.path.join(settings.media_root, "Downloads")
    file_name = ""
    if catalog_id:
        result = await db.execute(select(DownloadCatalog).where(DownloadCatalog.id == catalog_id))
        entry = result.scalar_one_or_none()
        if entry:
            title_out = entry.title
            year_out = entry.year
            safe_title = "".join(c if c.isalnum() or c in " ._-" else "" for c in title_out).strip()
            if is_season and season_name:
                dest_dir = os.path.join(settings.media_root, "Series", f"{safe_title} ({year_out})", season_name)
            elif entry.title_type == "movie":
                dest_dir = os.path.join(settings.media_root, "Movies", f"{safe_title} ({year_out})")
            else:
                dest_dir = os.path.join(settings.media_root, "Series", f"{safe_title} ({year_out})")
    if not looks_like_media_url(url):
        logger.info(f"Fetching season page: {url}")
        season_files = await fetch_season_page(url)
        if not season_files:
            raise HTTPException(status_code=400, detail="Could not parse season page")
        mkv_files = [f for f in season_files if f["name"].endswith(".mkv")]
        if not mkv_files:
            raise HTTPException(status_code=400, detail="No MKV files found on season page")
        created_tasks = []
        for sf in mkv_files:
            episode_url = urllib.parse.urljoin(_ensure_trailing_slash(url), sf["url"])
            episode_name = sf["name"]
            task = await _queue_download(db, user, episode_url, dest_dir, title_out, quality_label, catalog_id or None, episode_name)
            if task:
                created_tasks.append(task)
        if not created_tasks:
            raise HTTPException(status_code=500, detail="Failed to queue any episodes")
        await db.commit()
        logger.info("Season download queued: title=%s episodes=%d user=%s", title_out, len(created_tasks), user.username)
        return {
            "success": True,
            "tasks": [{"task_id": t.id, "aria2_gid": t.aria2_gid, "file_name": t.file_name} for t in created_tasks],
            "count": len(created_tasks),
        }
    task = await _queue_download(db, user, url, dest_dir, title_out, quality_label, catalog_id or None, file_name, scheduled_at or None, speed_limit)
    if not task:
        logger.warning("Create download - aria2 queue failed: url=%s user=%s", url[:80], user.username)
        raise HTTPException(status_code=500, detail="Failed to queue download in aria2")
    await db.commit()
    await db.refresh(task)
    logger.info("Download queued: task_id=%d title=%s user=%s", task.id, title_out, user.username)
    return {"success": True, "task_id": task.id, "aria2_gid": task.aria2_gid}


@router.get("/api/season-preview")
async def season_preview(
    url: str = Query(""),
    user: User = Depends(get_current_user),
):
    logger.debug("Season preview: url=%s user=%s", url[:80], user.username)
    if not url:
        logger.warning("Season preview - URL required: user=%s", user.username)
        raise HTTPException(status_code=400, detail="URL required")
    season_files = await fetch_season_page(url)
    if not season_files:
        raise HTTPException(status_code=400, detail="Could not parse season page")
    mkv_files = [f for f in season_files if f["name"].endswith(".mkv")]
    return {
        "success": True,
        "files": [
            {"name": f["name"], "url": urllib.parse.urljoin(_ensure_trailing_slash(url), f["url"]), "size": f["size"]}
            for f in mkv_files
        ],
        "count": len(mkv_files),
    }


# ============ LIST DOWNLOADS ============

@router.get("/api/downloads")
async def list_downloads(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    logger.debug("List downloads: user=%s", user.username)
    stmt = (
        select(DownloadTask, DownloadCatalog.cover_url, DownloadCatalog.imdb_code)
        .outerjoin(DownloadCatalog, DownloadTask.catalog_id == DownloadCatalog.id)
        .where(DownloadTask.user_id == user.id)
        .order_by(DownloadTask.created_at.desc())
        .limit(50)
    )
    result = await db.execute(stmt)
    rows = result.all()
    tasks = [r[0] for r in rows]
    cover_map = {r[0].id: {"cover_url": r[1] or "", "imdb_code": r[2] or ""} for r in rows}
    for t in tasks:
        await _sync_task_progress(t)
    downloads_data = [_task_to_dict(t, cover_map) for t in tasks]
    try:
        await db.commit()
    except StaleDataError:
        await db.rollback()
    return {"success": True, "downloads": downloads_data}


# ============ SEARCH / STATS ============

@router.get("/api/downloads/search")
async def search_downloads(
    q: str = Query(""),
    status_filter: str = Query(""),
    sort_by: str = Query("created_at"),
    sort_order: str = Query("desc"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Search downloads with filtering and sorting."""
    logger.debug("Search downloads: q=%s status=%s user=%s", q, status_filter, user.username)
    stmt = (
        select(DownloadTask, DownloadCatalog.cover_url, DownloadCatalog.imdb_code)
        .outerjoin(DownloadCatalog, DownloadTask.catalog_id == DownloadCatalog.id)
        .where(DownloadTask.user_id == user.id)
    )
    if q:
        stmt = stmt.where(DownloadTask.title.ilike(f"%{q}%"))
    if status_filter:
        statuses = [s.strip() for s in status_filter.split(",")]
        stmt = stmt.where(DownloadTask.status.in_(statuses))
    sort_col = getattr(DownloadTask, sort_by, DownloadTask.created_at)
    stmt = stmt.order_by(sort_col.asc() if sort_order == "asc" else sort_col.desc())
    result = await db.execute(stmt)
    rows = result.all()
    tasks = [r[0] for r in rows]
    cover_map = {r[0].id: {"cover_url": r[1] or "", "imdb_code": r[2] or ""} for r in rows}
    downloads_data = [
        {
            "id": t.id, "title": t.title, "file_name": t.file_name,
            "status": t.status, "progress_pct": t.progress_pct,
            "total_bytes": t.total_bytes, "downloaded_bytes": t.downloaded_bytes,
            "speed": t.speed, "quality_label": t.quality_label,
            "created_at": t.created_at.isoformat() if t.created_at else None,
            "error_message": t.error_message,
            "cover_url": cover_map.get(t.id, {}).get("cover_url", ""),
            "imdb_code": cover_map.get(t.id, {}).get("imdb_code", ""),
            "dest_path": t.dest_path,
            "scheduled_at": t.scheduled_at.isoformat() if t.scheduled_at else None,
            "speed_limit": t.speed_limit,
        }
        for t in tasks
    ]
    return {"success": True, "downloads": downloads_data, "count": len(downloads_data)}


@router.get("/api/downloads/stats")
async def download_stats(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Return aggregate download statistics."""
    logger.debug("Download stats: user=%s", user.username)
    result = await db.execute(select(DownloadTask).where(DownloadTask.user_id == user.id))
    tasks = result.scalars().all()
    stats = {"total": len(tasks), "downloading": 0, "completed": 0, "failed": 0, "paused": 0, "queued": 0, "interrupted": 0, "total_bytes": 0, "downloaded_bytes": 0, "has_active": False}
    for t in tasks:
        s = t.status
        if s in ("downloading", "active"):
            stats["downloading"] += 1
            stats["has_active"] = True
        elif s == "completed":
            stats["completed"] += 1
        elif s == "error":
            stats["failed"] += 1
        elif s == "paused":
            stats["paused"] += 1
        elif s in ("queued", "waiting"):
            stats["queued"] += 1
        elif s == "interrupted":
            stats["interrupted"] += 1
        try:
            stats["total_bytes"] += int(t.total_bytes or 0)
            stats["downloaded_bytes"] += int(t.downloaded_bytes or 0)
        except (ValueError, TypeError):
            pass
    stats["progress_pct"] = round(stats["downloaded_bytes"] / stats["total_bytes"] * 100, 1) if stats["total_bytes"] > 0 else 0
    return {"success": True, "stats": stats}


# ============ SSE FOR DOWNLOAD PROGRESS ============

async def _download_event_generator(user_id: int, request: Request):
    """Generate SSE events for download progress."""
    from sse_starlette.sse import EventSourceResponse
    last_statuses = {}
    while True:
        if await request.is_disconnected():
            break
        try:
            async with async_session() as db:
                from sqlalchemy import select
                stmt = (
                    select(DownloadTask, DownloadCatalog.cover_url, DownloadCatalog.imdb_code)
                    .outerjoin(DownloadCatalog, DownloadTask.catalog_id == DownloadCatalog.id)
                    .where(DownloadTask.user_id == user_id)
                    .order_by(DownloadTask.created_at.desc())
                    .limit(50)
                )
                result = await db.execute(stmt)
                rows = result.all()
                tasks = [r[0] for r in rows]
                for t in tasks:
                    await _sync_task_progress(t)

                await db.commit()

                cover_map = {r[0].id: {"cover_url": r[1] or "", "imdb_code": r[2] or ""} for r in rows}
                current_statuses = {}
                for t in tasks:
                    sid = t.id
                    st = t.status
                    current_statuses[sid] = st
                    prev = last_statuses.get(sid)
                    if prev and prev != st:
                        if st == "completed":
                            yield {"event": "completed", "data": json.dumps({
                                "id": sid, "title": t.title,
                                "file_name": t.file_name or "",
                                "dest_path": t.dest_path or "",
                            })}
                        elif st == "error":
                            yield {"event": "failed", "data": json.dumps({"id": sid, "title": t.title, "error": t.error_message})}
                last_statuses.update(current_statuses)

                downloads_data = [_task_to_dict(t, cover_map) for t in tasks]
                yield {"event": "progress", "data": json.dumps({"downloads": downloads_data})}
        except Exception as e:
            logger.warning(f"SSE poll error: {e}")
        await asyncio.sleep(2)


@router.get("/api/downloads/sse")
async def download_sse(request: Request, token: str = Query("")):
    from sse_starlette.sse import EventSourceResponse
    if not token:
        from fastapi import HTTPException as HE
        raise HE(status_code=401, detail="Token required")
    try:
        from app.dependencies import decode_token
        payload = decode_token(token)
    except Exception:
        from fastapi import HTTPException as HE
        raise HE(status_code=401, detail="Invalid token")
    async with async_session() as db:
        from sqlalchemy import select
        from app.models.user import User
        result = await db.execute(select(User).where(User.id == int(payload["sub"])))
        user = result.scalar_one_or_none()
        if not user:
            from fastapi import HTTPException as HE
            raise HE(status_code=401, detail="User not found")
    return EventSourceResponse(_download_event_generator(user.id, request))


# ============ DOWNLOAD STATUS ============

@router.get("/api/downloads/{task_id}")
async def download_status(task_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    logger.debug("Download status: task_id=%d user=%s", task_id, user.username)
    result = await db.execute(select(DownloadTask).where(DownloadTask.id == task_id, DownloadTask.user_id == user.id))
    task = result.scalar_one_or_none()
    if not task:
        logger.warning("Download status - task not found: task_id=%d user=%s", task_id, user.username)
        raise HTTPException(status_code=404)
    await _sync_task_progress(task)
    try:
        await db.commit()
    except StaleDataError:
        await db.rollback()
    return {
        "success": True,
        "download": {
            "id": task.id, "title": task.title,
            "file_name": task.file_name, "status": task.status,
            "progress_pct": task.progress_pct,
            "total_bytes": task.total_bytes,
            "downloaded_bytes": task.downloaded_bytes,
            "speed": task.speed, "quality_label": task.quality_label,
            "error_message": task.error_message,
        },
    }


# ============ DOWNLOAD ACTIONS ============

@router.post("/api/downloads/{task_id}/open")
async def open_download_file(task_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    logger.info("Open download file: task_id=%d user=%s", task_id, user.username)
    result = await db.execute(select(DownloadTask).where(DownloadTask.id == task_id, DownloadTask.user_id == user.id))
    task = result.scalar_one_or_none()
    if not task:
        logger.warning("Open file - task not found: task_id=%d user=%s", task_id, user.username)
        raise HTTPException(status_code=404)
    if not task.dest_path:
        raise HTTPException(status_code=400, detail="No file path for this download")
    # Open file in system file manager
    try:
        import subprocess, platform, os
        path = task.dest_path
        if platform.system() == "Windows":
            subprocess.Popen(["explorer", "/select,", path])
        elif platform.system() == "Darwin":
            subprocess.Popen(["open", "-R", path])
        else:
            # Linux: open parent directory in default file manager
            parent = os.path.dirname(path)
            subprocess.Popen(["xdg-open", parent])
        return {"success": True, "detail": "Opened in file browser"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/api/downloads/{task_id}/pause")
async def pause_download_endpoint(task_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    logger.info("Pause download: task_id=%d user=%s", task_id, user.username)
    result = await db.execute(select(DownloadTask).where(DownloadTask.id == task_id, DownloadTask.user_id == user.id))
    task = result.scalar_one_or_none()
    if not task:
        logger.warning("Pause - task not found: task_id=%d user=%s", task_id, user.username)
        raise HTTPException(status_code=404)
    if task.aria2_gid:
        ok = await pause_download(task.aria2_gid)
        if ok:
            task.status = "paused"
            await db.commit()
            return {"success": True}
        raise HTTPException(status_code=500, detail="Failed to pause download")
    raise HTTPException(status_code=400, detail="No aria2 task")


@router.put("/api/downloads/{task_id}/resume")
async def resume_download_endpoint(task_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    logger.info("Resume download: task_id=%d user=%s", task_id, user.username)
    result = await db.execute(select(DownloadTask).where(DownloadTask.id == task_id, DownloadTask.user_id == user.id))
    task = result.scalar_one_or_none()
    if not task:
        logger.warning("Resume - task not found: task_id=%d user=%s", task_id, user.username)
        raise HTTPException(status_code=404)
    if task.aria2_gid:
        ok = await resume_download(task.aria2_gid)
        if ok:
            task.status = "downloading"
            await db.commit()
            return {"success": True}
        raise HTTPException(status_code=500, detail="Failed to resume download")
    raise HTTPException(status_code=400, detail="No aria2 task")


@router.post("/api/downloads/{task_id}/restart")
async def restart_download(
    task_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    logger.info("Restart download: task_id=%d user=%s", task_id, user.username)
    result = await db.execute(select(DownloadTask).where(DownloadTask.id == task_id, DownloadTask.user_id == user.id))
    task = result.scalar_one_or_none()
    if not task:
        logger.warning("Restart - task not found: task_id=%d user=%s", task_id, user.username)
        raise HTTPException(status_code=404)
    aria2_gid = await add_download(task.url, task.dest_path, task.file_name)
    if not aria2_gid:
        raise HTTPException(status_code=500, detail="Failed to restart download in aria2")
    task.aria2_gid = aria2_gid
    task.status = "downloading"
    task.progress_pct = 0.0
    task.total_bytes = "0"
    task.downloaded_bytes = "0"
    task.speed = ""
    task.error_message = ""
    await db.commit()
    return {"success": True, "task_id": task.id, "aria2_gid": aria2_gid}


@router.put("/api/downloads/{task_id}/speed-limit")
async def set_speed_limit_endpoint(
    task_id: int,
    speed: str = Query("0", description="Speed in bytes/sec (0 = unlimited)"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    logger.info("Set speed limit: task_id=%d speed=%s user=%s", task_id, speed, user.username)
    result = await db.execute(select(DownloadTask).where(DownloadTask.id == task_id, DownloadTask.user_id == user.id))
    task = result.scalar_one_or_none()
    if not task:
        logger.warning("Set speed limit - task not found: task_id=%d user=%s", task_id, user.username)
        raise HTTPException(status_code=404)
    task.speed_limit = speed
    if task.aria2_gid:
        await set_speed_limit_rpc(task.aria2_gid, speed)
    await db.commit()
    return {"success": True}


@router.put("/api/downloads/{task_id}/schedule")
async def update_schedule(
    task_id: int,
    scheduled_at: str = Query(""),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    logger.info("Update schedule: task_id=%d scheduled_at=%s user=%s", task_id, scheduled_at, user.username)
    result = await db.execute(select(DownloadTask).where(DownloadTask.id == task_id, DownloadTask.user_id == user.id))
    task = result.scalar_one_or_none()
    if not task:
        logger.warning("Update schedule - task not found: task_id=%d user=%s", task_id, user.username)
        raise HTTPException(status_code=404)
    if scheduled_at:
        try:
            task.scheduled_at = datetime.datetime.fromisoformat(scheduled_at)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid datetime format")
    else:
        task.scheduled_at = None
    await db.commit()
    return {"success": True}


# ============ BATCH OPERATIONS ============

@router.post("/api/downloads/batch/retry")
async def retry_all_failed(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    logger.info("Batch retry all failed: user=%s", user.username)
    result = await db.execute(
        select(DownloadTask).where(
            DownloadTask.user_id == user.id,
            DownloadTask.status.in_(["error", "interrupted"]),
            DownloadTask.url != "",
        )
    )
    tasks = result.scalars().all()
    count = 0
    for t in tasks:
        new_gid = await add_download(t.url, t.dest_path, t.file_name)
        if new_gid:
            t.aria2_gid = new_gid
            t.status = "downloading"
            t.error_message = ""
            t.progress_pct = 0.0
            t.total_bytes = "0"
            t.downloaded_bytes = "0"
            t.speed = ""
            count += 1
    await db.commit()
    logger.info("Batch retry result: retried=%d user=%s", count, user.username)
    return {"success": True, "retried": count}


@router.post("/api/downloads/batch/pause")
async def pause_all(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    logger.info("Batch pause all: user=%s", user.username)
    result = await db.execute(
        select(DownloadTask).where(DownloadTask.user_id == user.id, DownloadTask.status == "downloading")
    )
    tasks = result.scalars().all()
    count = 0
    for t in tasks:
        if t.aria2_gid:
            ok = await pause_download(t.aria2_gid)
            if ok:
                t.status = "paused"
                count += 1
    await db.commit()
    logger.info("Batch pause result: paused=%d user=%s", count, user.username)
    return {"success": True, "paused": count}


@router.post("/api/downloads/batch/resume")
async def resume_all(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    logger.info("Batch resume all: user=%s", user.username)
    result = await db.execute(
        select(DownloadTask).where(DownloadTask.user_id == user.id, DownloadTask.status == "paused")
    )
    tasks = result.scalars().all()
    count = 0
    for t in tasks:
        if t.aria2_gid:
            ok = await resume_download(t.aria2_gid)
            if ok:
                t.status = "downloading"
                count += 1
    await db.commit()
    logger.info("Batch resume result: resumed=%d user=%s", count, user.username)
    return {"success": True, "resumed": count}


# ============ MANUAL DOWNLOAD ============

VIDEO_EXTENSIONS = {".mkv", ".mp4", ".avi", ".mov", ".webm", ".m4v", ".flv", ".wmv", ".ts", ".mts", ".vob"}


class ManualDownloadRequest(BaseModel):
    url: str
    title: str = ""
    quality_label: str = "Manual"
    catalog_id: int = 0
    scheduled_at: str = ""


@router.post("/api/downloads/manual")
async def manual_download(
    body: ManualDownloadRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Add a download from a manually entered URL.
    Validates the URL looks like a video file, then queues it.
    """
    url = body.url
    title = body.title
    quality_label = body.quality_label
    catalog_id = body.catalog_id
    scheduled_at = body.scheduled_at
    logger.info("Manual download: url=%s title=%s user=%s", url[:80], title, user.username)
    if not url:
        raise HTTPException(status_code=400, detail="URL required")

    # Validate URL looks like a video
    parsed = urllib.parse.urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        raise HTTPException(status_code=400, detail="Invalid URL")

    ext = os.path.splitext(parsed.path)[1].lower()
    is_video = ext in VIDEO_EXTENSIONS

    title_out = title.strip() or os.path.splitext(os.path.basename(parsed.path))[0] or "Manual Download"
    dest_dir = os.path.join(settings.media_root, "Downloads", "Manual")

    if is_video:
        # Direct video file URL
        task = await _queue_download(db, user, url, dest_dir, title_out, quality_label, catalog_id or None)
        if not task:
            raise HTTPException(status_code=500, detail="Failed to queue download in aria2")
        await db.commit()
        await db.refresh(task)
        logger.info("Manual download queued: task_id=%d title=%s user=%s", task.id, title_out, user.username)
        return {"success": True, "task_id": task.id, "aria2_gid": task.aria2_gid, "detected": True, "type": "video"}
    else:
        # Not a direct video URL — try to probe it
        try:
            proc = await asyncio.create_subprocess_exec(
                "aria2c", "--dry-run", "--console-log-level=error", url,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                timeout=15,
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode == 0 and stdout:
                # Parse aria2 output to find filename
                for line in stdout.decode().splitlines():
                    if "FILE" in line or "file" in line:
                        continue
            task = await _queue_download(db, user, url, dest_dir, title_out, quality_label, catalog_id or None)
            if not task:
                raise HTTPException(status_code=500, detail="Failed to queue download")
            await db.commit()
            await db.refresh(task)
            return {"success": True, "task_id": task.id, "aria2_gid": task.aria2_gid, "detected": False, "type": "direct"}
        except Exception:
            # Last resort — just queue it as-is
            task = await _queue_download(db, user, url, dest_dir, title_out, quality_label, catalog_id or None)
            if not task:
                raise HTTPException(status_code=500, detail="Failed to queue download")
            await db.commit()
            await db.refresh(task)
            return {"success": True, "task_id": task.id, "aria2_gid": task.aria2_gid, "detected": False, "type": "unknown"}


@router.post("/api/downloads/batch/cancel")
async def cancel_all(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    logger.info("Batch cancel all: user=%s", user.username)
    result = await db.execute(
        select(DownloadTask).where(
            DownloadTask.user_id == user.id,
            DownloadTask.status.in_(["downloading", "paused"]),
        )
    )
    tasks = result.scalars().all()
    count = 0
    for t in tasks:
        if t.aria2_gid:
            await cancel_download(t.aria2_gid)
        await db.delete(t)
        count += 1
    await db.commit()
    logger.info("Batch cancel result: cancelled=%d user=%s", count, user.username)
    return {"success": True, "cancelled": count}


@router.delete("/api/downloads/{task_id}")
async def delete_download(
    task_id: int,
    delete_files: bool = Query(False),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    logger.info("Delete download: task_id=%d delete_files=%s user=%s", task_id, delete_files, user.username)
    result = await db.execute(select(DownloadTask).where(DownloadTask.id == task_id, DownloadTask.user_id == user.id))
    task = result.scalar_one_or_none()
    if not task:
        logger.warning("Delete download - task not found: task_id=%d user=%s", task_id, user.username)
        raise HTTPException(status_code=404)
    if task.aria2_gid:
        await cancel_download(task.aria2_gid)
    deleted_files = []
    if delete_files and task.dest_path:
        file_path = os.path.normpath(os.path.join(task.dest_path, task.file_name))
        if os.path.exists(file_path) and file_path.startswith(os.path.normpath(settings.media_root)):
            try:
                os.remove(file_path)
                deleted_files.append(task.file_name)
            except Exception as e:
                logger.warning(f"Failed to delete file {file_path}: {e}")
    await db.delete(task)
    await db.commit()
    return {"success": True, "deleted_files": deleted_files}
