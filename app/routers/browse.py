import os
import time
import logging
import shutil
import zipfile
import io
import json
import asyncio
import aiofiles
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, Depends, Query, HTTPException, UploadFile, File, Form
from fastapi.responses import JSONResponse, StreamingResponse
from werkzeug.utils import safe_join
from concurrent.futures import ThreadPoolExecutor

from app.config import settings
from app.dependencies import get_current_user
from app.models.user import User

logger = logging.getLogger(__name__)
router = APIRouter(tags=["browse"])
_pool = ThreadPoolExecutor(max_workers=2)

# LRU caches with max size
from collections import OrderedDict


class LRUCache:
    def __init__(self, maxsize=100, ttl=300):
        self.maxsize = maxsize
        self.ttl = ttl
        self._cache: OrderedDict = OrderedDict()

    def get(self, key):
        if key not in self._cache:
            return None
        ts, val = self._cache[key]
        if time.time() - ts > self.ttl:
            del self._cache[key]
            return None
        self._cache.move_to_end(key)
        return val

    def set(self, key, val):
        if len(self._cache) >= self.maxsize:
            self._cache.popitem(last=False)
        self._cache[key] = (time.time(), val)

    def invalidate(self, prefix=""):
        if not prefix:
            self._cache.clear()
        else:
            to_del = [k for k in self._cache if k.startswith(prefix)]
            for k in to_del:
                del self._cache[k]


dir_cache = LRUCache(maxsize=200, ttl=30)
all_media_cache = LRUCache(maxsize=1, ttl=30)
CACHE_TTL = 30

TEXT_EXTENSIONS = {"txt", "md", "log", "json", "xml", "yaml", "yml", "csv", "ini", "cfg", "conf", "nfo", "srt", "sub", "ass", "py", "js", "ts", "html", "css", "sh", "bat", "ps1", "env", "gitignore", "dockerfile", "toml"}

def _fmt_size(b):
    if b is None: return ''
    for u in ('B','KB','MB','GB','TB'):
        if b < 1024: return f"{b:.1f} {u}"
        b /= 1024
    return f"{b:.1f} PB"


def is_allowed_file(filename: str) -> bool:
    return True  # Allow all file types


def get_file_type(filename: str) -> str:
    ext = filename.rsplit(".", 1)[1].lower()
    if ext in settings.allowed_images:
        return "image"
    if ext in settings.allowed_videos:
        return "video"
    if ext in settings.allowed_audio:
        return "audio"
    if ext in TEXT_EXTENSIONS:
        return "text"
    return "other"


def resolve_subpath(subpath: str) -> Optional[str]:
    if subpath:
        safe = safe_join(settings.media_root, subpath)
        if safe and os.path.exists(safe):
            return str(Path(safe).resolve())
        return None
    return str(Path(settings.media_root).resolve())


def get_directory_contents(subpath: str = "", force_refresh: bool = False):
    cache_key = f"dir_{subpath}"
    if not force_refresh:
        cached = dir_cache.get(cache_key)
        if cached is not None:
            return cached
    resolved = resolve_subpath(subpath)
    if not resolved or not os.path.isdir(resolved):
        return None
    try:
        items = []
        with os.scandir(resolved) as entries:
            for entry in entries:
                is_dir = entry.is_dir()
                rel = os.path.join(subpath, entry.name).replace("\\", "/") if subpath else entry.name
                stat = entry.stat()
                item = {
                    "name": entry.name,
                    "path": rel,
                    "is_dir": is_dir,
                    "type": "directory" if is_dir else get_file_type(entry.name) if "." in entry.name else "other",
                    "is_media": not is_dir and is_allowed_file(entry.name),
                    "size": stat.st_size if not is_dir else 0,
                    "modified": stat.st_mtime,
                    "ext": entry.name.split(".")[-1].lower() if "." in entry.name else "",
                }
                items.append(item)
        items.sort(key=lambda x: (not x["is_dir"], x["name"].lower()))
        dir_cache.set(cache_key, items)
        return items
    except Exception as e:
        logger.error(f"Browse error: {e}")
        return None


async def get_all_media_files():
    cached = all_media_cache.get("all")
    if cached is not None:
        return cached

    def _walk():
        files = []
        try:
            for root, _dirs, fnames in os.walk(settings.media_root):
                for fname in fnames:
                    if is_allowed_file(fname):
                        rel = os.path.relpath(os.path.join(root, fname), settings.media_root).replace("\\", "/")
                        files.append({
                            "name": fname,
                            "path": rel,
                            "type": get_file_type(fname),
                            "ext": fname.split(".")[-1].lower(),
                        })
        except Exception as e:
            logger.error(f"Media scan error: {e}")
        return files

    loop = asyncio.get_event_loop()
    files = await loop.run_in_executor(_pool, _walk)
    all_media_cache.set("all", files)
    return files


@router.get("/api/browse/{subpath:path}")
@router.get("/api/browse/")
async def api_browse(subpath: str = "", refresh: bool = Query(False), user: User = Depends(get_current_user)):
    logger.debug("Browse directory: subpath=%s refresh=%s user=%s", subpath, refresh, user.username)
    items = get_directory_contents(subpath, refresh)
    if items is None:
        logger.warning("Browse directory not found: subpath=%s user=%s", subpath, user.username)
        return JSONResponse({"success": False, "error": "Not found"}, status_code=404)

    # Merge AI category info for media files
    media_paths = [it["path"] for it in items if it.get("is_media")]
    if media_paths:
        from app.database import async_session
        from app.services.file_categorizer import get_categories_for_paths
        async with async_session() as db:
            cats = await get_categories_for_paths(db, media_paths)
            for it in items:
                info = cats.get(it["path"])
                if info:
                    it["category"] = info["category"]
                    it["genre"] = info["genre"]
                    it["year"] = info["year"]
                else:
                    it["category"] = None
                    it["genre"] = None
                    it["year"] = None

    parent = "/".join(subpath.split("/")[:-1]) if subpath else ""
    resolved = resolve_subpath(subpath) or settings.media_root
    disk = shutil.disk_usage(resolved)
    total_files = sum(1 for it in items if not it["is_dir"])
    total_size = sum(it["size"] for it in items if not it["is_dir"])
    logger.debug("Browse result: subpath=%s items=%d files=%d user=%s", subpath, len(items), total_files, user.username)
    return {
        "success": True,
        "items": items,
        "current_path": subpath,
        "parent_path": parent,
        "stats": {
            "total_items": len(items),
            "total_files": total_files,
            "total_dirs": len(items) - total_files,
            "total_size": total_size,
            "total_size_fmt": _fmt_size(total_size),
        },
        "disk": {
            "total": disk.total,
            "used": disk.used,
            "free": disk.free,
            "free_fmt": _fmt_size(disk.free),
            "used_fmt": _fmt_size(disk.used),
        },
    }


@router.get("/api/files")
async def api_files(page: int = Query(1), per_page: int = Query(30), user: User = Depends(get_current_user)):
    logger.debug("List files: page=%d per_page=%d user=%s", page, per_page, user.username)
    files = await get_all_media_files()
    total = len(files)
    start = (page - 1) * per_page
    end = start + per_page
    paginated = files[start:end]

    # Merge AI category info
    media_paths = [f["path"] for f in paginated]
    if media_paths:
        from app.database import async_session
        from app.services.file_categorizer import get_categories_for_paths
        async with async_session() as db:
            cats = await get_categories_for_paths(db, media_paths)
            for f in paginated:
                info = cats.get(f["path"])
                if info:
                    f["category"] = info["category"]
                    f["genre"] = info["genre"]
                    f["year"] = info["year"]
                else:
                    f["category"] = None
                    f["genre"] = None
                    f["year"] = None

    logger.debug("Files listed: total=%d returned=%d user=%s", total, len(paginated), user.username)
    return {
        "success": True,
        "files": paginated,
        "total": total,
        "has_more": end < total,
        "page": page,
    }


@router.get("/api/search")
async def api_search(q: str = Query(""), user: User = Depends(get_current_user)):
    logger.debug("Search files: q=%s user=%s", q, user.username)
    if len(q) < 2:
        logger.debug("Search query too short: q=%s", q)
        return {"success": False, "error": "Query too short"}
    files = await get_all_media_files()
    results = [f for f in files if q.lower() in f["name"].lower()]
    logger.debug("Search results: q=%s hits=%d user=%s", q, len(results), user.username)
    return {"success": True, "results": results[:50]}


@router.post("/api/file/covers")
async def batch_file_covers(
    paths: list[str] = Query([]),
    user: User = Depends(get_current_user),
):
    """Given file paths (relative to media_root), return matching cover_urls."""
    logger.debug("Batch file covers: paths=%d user=%s", len(paths), user.username)
    from app.database import async_session
    from app.models.download_task import DownloadTask
    from app.models.download_catalog import DownloadCatalog
    from sqlalchemy import select

    all_paths = list(paths)
    if not all_paths:
        return {"success": True, "covers": {}}
    result = {}
    async with async_session() as db:
        stmt = (
            select(DownloadCatalog.cover_url, DownloadTask.dest_path)
            .join(DownloadTask, DownloadTask.catalog_id == DownloadCatalog.id)
            .where(DownloadCatalog.cover_url != "")
        )
        rows = await db.execute(stmt)
        for cover_url, dest_path in rows.all():
            if not dest_path:
                continue
            norm = dest_path.replace("\\", "/")
            for p in all_paths:
                if p in norm and p not in result:
                    result[p] = cover_url
    return {"success": True, "covers": result}


# ── File Explorer Features ──────────────────────────────

@router.post("/api/upload/{subpath:path}")
@router.post("/api/upload/")
async def upload_file(
    file: UploadFile = File(...),
    subpath: str = "",
    user: User = Depends(get_current_user),
):
    logger.info("Upload file: name=%s subpath=%s user=%s", file.filename, subpath, user.username)
    dest_dir = resolve_subpath(subpath)
    if not dest_dir or not os.path.isdir(dest_dir):
        logger.warning("Upload directory not found: subpath=%s user=%s", subpath, user.username)
        raise HTTPException(status_code=404, detail="Directory not found")
    dest = os.path.join(dest_dir, file.filename)
    if file.size is not None and file.size == 0:
        raise HTTPException(status_code=400, detail="Cannot upload empty file")
    try:
        contents = await file.read()
        if len(contents) == 0:
            raise HTTPException(status_code=400, detail="Cannot upload empty file")
        with open(dest, "wb") as f:
            f.write(contents)
        dir_cache.invalidate(prefix=f"dir_{subpath}")
        return {"success": True, "path": os.path.join(subpath, file.filename).replace("\\", "/")}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/api/delete")
async def delete_item(
    path: str = Query(...),
    user: User = Depends(get_current_user),
):
    logger.info("Delete item: path=%s user=%s", path, user.username)
    resolved = resolve_subpath(path)
    if not resolved:
        logger.warning("Delete - path not found: %s user=%s", path, user.username)
        raise HTTPException(status_code=404, detail="Not found")
    try:
        if os.path.isdir(resolved):
            shutil.rmtree(resolved)
        else:
            os.remove(resolved)
        parent = "/".join(path.split("/")[:-1]) if path else ""
        dir_cache.invalidate(prefix="dir_")
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/api/rename")
async def rename_item(
    path: str = Query(...),
    new_name: str = Query(...),
    user: User = Depends(get_current_user),
):
    logger.info("Rename item: path=%s new_name=%s user=%s", path, new_name, user.username)
    resolved = resolve_subpath(path)
    if not resolved:
        logger.warning("Rename - path not found: %s user=%s", path, user.username)
        raise HTTPException(status_code=404, detail="Not found")
    parent = os.path.dirname(resolved)
    dest = os.path.join(parent, new_name)
    if os.path.exists(dest):
        raise HTTPException(status_code=400, detail="Target name already exists")
    try:
        os.rename(resolved, dest)
        dir_cache.invalidate(prefix="dir_")
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/mkdir")
async def create_directory(
    path: str = Query(...),
    name: str = Query(...),
    user: User = Depends(get_current_user),
):
    logger.info("Create directory: parent=%s name=%s user=%s", path, name, user.username)
    parent = resolve_subpath(path)
    if not parent or not os.path.isdir(parent):
        logger.warning("Mkdir - parent not found: %s user=%s", path, user.username)
        raise HTTPException(status_code=404, detail="Parent directory not found")
    dest = os.path.join(parent, name)
    if os.path.exists(dest):
        raise HTTPException(status_code=400, detail="Already exists")
    try:
        os.makedirs(dest, exist_ok=True)
        dir_cache.invalidate(prefix=f"dir_{path}")
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/move")
async def move_item(
    source: str = Query(...),
    dest: str = Query(...),
    user: User = Depends(get_current_user),
):
    logger.info("Move item: source=%s dest=%s user=%s", source, dest, user.username)
    src_resolved = resolve_subpath(source)
    if not src_resolved:
        logger.warning("Move - source not found: %s user=%s", source, user.username)
        raise HTTPException(status_code=404, detail="Source not found")
    dest_resolved = resolve_subpath(dest)
    if not dest_resolved or not os.path.isdir(dest_resolved):
        raise HTTPException(status_code=404, detail="Destination directory not found")
    target = os.path.join(dest_resolved, os.path.basename(src_resolved))
    try:
        shutil.move(src_resolved, target)
        dir_cache.invalidate(prefix="dir_")
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/download-zip")
async def download_zip(
    path: str = Query(""),
    user: User = Depends(get_current_user),
):
    logger.debug("Download zip: path=%s user=%s", path, user.username)
    resolved = resolve_subpath(path)
    if not resolved:
        logger.warning("Download zip - path not found: %s user=%s", path, user.username)
        raise HTTPException(status_code=404, detail="Not found")

    buf = io.BytesIO()
    arcname = os.path.basename(resolved) or "download"

    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        if os.path.isdir(resolved):
            for root, _dirs, files in os.walk(resolved):
                for fname in files:
                    fpath = os.path.join(root, fname)
                    rel = os.path.relpath(fpath, os.path.dirname(resolved))
                    zf.write(fpath, rel)
        else:
            zf.write(resolved, arcname)

    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{arcname}.zip"'},
    )


@router.get("/api/enrich/{subpath:path}")
async def enrich_file(subpath: str = "", user: User = Depends(get_current_user)):
    logger.debug("Enrich file: subpath=%s user=%s", subpath, user.username)
    from app.services.metadata_enricher import enrich_media_by_filename
    data = await enrich_media_by_filename(subpath)
    logger.debug("Enrich result: subpath=%s has_data=%s", subpath, bool(data))
    return {"success": True, "metadata": data}


@router.get("/api/enrich-batch")
async def enrich_files_batch(paths: str = Query(""), user: User = Depends(get_current_user)):
    logger.debug("Enrich batch: paths=%s user=%s", paths[:100], user.username)
    from app.services.metadata_enricher import enrich_media_by_filename
    items = [p.strip() for p in paths.split(",") if p.strip()]
    results = {}
    for p in items:
        try:
            data = await enrich_media_by_filename(p)
            if data:
                results[p] = data
        except Exception as e:
            logger.warning("Enrich batch item failed: path=%s error=%s user=%s", p, e, user.username)
    logger.debug("Enrich batch result: requested=%d succeeded=%d", len(items), len(results))
    return {"success": True, "metadata": results}


@router.get("/api/file-info/{subpath:path}")
async def file_info(subpath: str = "", user: User = Depends(get_current_user)):
    logger.debug("File info: subpath=%s user=%s", subpath, user.username)
    resolved = resolve_subpath(subpath)
    if not resolved:
        logger.warning("File info - not found: %s user=%s", subpath, user.username)
        raise HTTPException(status_code=404, detail="Not found")
    stat = os.stat(resolved)
    info = {
        "name": os.path.basename(resolved),
        "path": subpath,
        "is_dir": os.path.isdir(resolved),
        "size": stat.st_size,
        "modified": stat.st_mtime,
        "created": stat.st_ctime,
    }
    if not os.path.isdir(resolved):
        ext = resolved.rsplit(".", 1)[-1].lower() if "." in resolved else ""
        info["ext"] = ext
        info["type"] = get_file_type(resolved)
    return {"success": True, "info": info}


@router.get("/api/recent")
async def get_recent_files(days: int = Query(7), limit: int = Query(20)):
    """Return recently added/modified media files."""
    logger.debug("Recent files: days=%d limit=%d", days, limit)
    import time as _time
    cache_key = f"recent_{days}_{limit}"
    cached = dir_cache.get(cache_key)
    if cached is not None:
        return {"success": True, "items": cached}

    cutoff = _time.time() - (days * 86400)
    items = []
    try:
        for root, _dirs, fnames in os.walk(settings.media_root):
            for fname in fnames:
                if not is_allowed_file(fname) and get_file_type(fname) != "text":
                    continue
                fpath = os.path.join(root, fname)
                try:
                    st = os.stat(fpath)
                    if st.st_mtime >= cutoff:
                        rel = os.path.relpath(fpath, settings.media_root).replace("\\", "/")
                        items.append({
                            "name": fname,
                            "path": rel,
                            "type": get_file_type(fname),
                            "size": st.st_size,
                            "modified": st.st_mtime,
                        })
                except OSError:
                    pass
        items.sort(key=lambda x: x["modified"], reverse=True)
        items = items[:limit]
    except Exception as e:
        logger.error(f"Recent files scan error: {e}")
    dir_cache.set(cache_key, items)
    return {"success": True, "items": items}


@router.post("/api/browse/mkdir")
async def mkdir(
    body: dict,
    user: User = Depends(get_current_user),
):
    """Create a new directory."""
    path = body.get("path", "")
    logger.debug("Mkdir: path=%s user=%s", path, user.username)
    safe = safe_join(settings.media_root, path.lstrip("/"))
    if not safe or not safe.startswith(os.path.normpath(settings.media_root)):
        raise HTTPException(403, "Invalid path")
    try:
        os.makedirs(safe, exist_ok=True)
        return {"success": True}
    except Exception as e:
        raise HTTPException(500, f"Failed to create directory: {e}")


# ── File Upload ──────────────────────────────────────────────────
_UPLOAD_SLOT = asyncio.Lock()


@router.post("/api/user-upload")
async def user_upload_file(
    file: UploadFile = File(...),
    path: str = Form(""),
    user: User = Depends(get_current_user),
):
    """Upload a file to /mnt/hdd/media/Uploads/{username}/[path]/"""
    logger.info("User upload: user=%s file=%s path=%s", user.username, file.filename, path)
    base = os.path.join(settings.media_root, "Uploads", user.username)
    os.makedirs(base, exist_ok=True)
    dest = os.path.normpath(os.path.join(base, path.strip("/"), file.filename or "unnamed"))
    if not dest.startswith(os.path.normpath(base)):
        raise HTTPException(403, "Invalid path")
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    async with _UPLOAD_SLOT:
        try:
            content = await file.read()
            async with aiofiles.open(dest, "wb") as f:
                await f.write(content)
            rel = os.path.relpath(dest, settings.media_root)
            dir_cache.invalidate(prefix="dir_Uploads/")
            logger.info("User upload complete: user=%s dest=%s size=%d", user.username, dest, len(content))
            return {"success": True, "path": rel, "size": len(content)}
        except Exception as e:
            logger.error("User upload failed: %s", e)
            raise HTTPException(500, f"Upload failed: {e}")


@router.post("/api/user-upload/chunk")
async def upload_chunk(
    file: UploadFile = File(...),
    path: str = Form(""),
    chunk_index: int = Form(0),
    total_chunks: int = Form(1),
    user: User = Depends(get_current_user),
):
    """Chunked upload — supports large files."""
    base = os.path.join(settings.media_root, "Uploads", user.username)
    os.makedirs(base, exist_ok=True)
    dest = os.path.normpath(os.path.join(base, path.strip("/"), file.filename or "unnamed"))
    if not dest.startswith(os.path.normpath(base)):
        raise HTTPException(403, "Invalid path")
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    chunk_dir = dest + ".chunks"
    os.makedirs(chunk_dir, exist_ok=True)
    chunk_path = os.path.join(chunk_dir, f"{chunk_index:06d}")
    try:
        content = await file.read()
        async with aiofiles.open(chunk_path, "wb") as f:
            await f.write(content)
    except Exception as e:
        raise HTTPException(500, f"Chunk write failed: {e}")
    # If last chunk, assemble
    if chunk_index == total_chunks - 1:
        try:
            async with aiofiles.open(dest, "wb") as out:
                for i in range(total_chunks):
                    cp = os.path.join(chunk_dir, f"{i:06d}")
                    if os.path.exists(cp):
                        async with aiofiles.open(cp, "rb") as cf:
                            while True:
                                b = await cf.read(65536)
                                if not b:
                                    break
                                await out.write(b)
                        os.remove(cp)
            os.rmdir(chunk_dir)
            dir_cache.invalidate(prefix="dir_Uploads/")
            logger.info("Chunked upload complete: %s (%d chunks)", dest, total_chunks)
        except Exception as e:
            raise HTTPException(500, f"Chunk assembly failed: {e}")
    return {"success": True, "chunk": chunk_index, "total": total_chunks}


@router.delete("/api/user-upload")
async def delete_uploaded(
    path: str = Query(...),
    user: User = Depends(get_current_user),
):
    """Delete a file or directory from Uploads."""
    base = os.path.join(settings.media_root, "Uploads", user.username)
    target = os.path.normpath(os.path.join(base, path.strip("/")))
    if not target.startswith(os.path.normpath(base)):
        raise HTTPException(403, "Invalid path")
    if not os.path.exists(target):
        raise HTTPException(404, "Not found")
    try:
        if os.path.isdir(target):
            shutil.rmtree(target)
        else:
            os.remove(target)
        dir_cache.invalidate(prefix="dir_Uploads/")
        return {"success": True}
    except Exception as e:
        raise HTTPException(500, f"Delete failed: {e}")
