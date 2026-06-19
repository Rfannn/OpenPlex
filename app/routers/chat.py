"""Chat and AI rename-suggest endpoints.

AI strategy:
  1. Try Agnes AI (primary — cloud, fast, always available)
  2. If Agnes fails (down, rate-limited), start local llama-server on-demand
  3. Local server auto-stops after 5 min idle to save resources
"""
import json
import os
import logging
import time
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.config import settings
from app.services import agnes_ai

logger = logging.getLogger(__name__)
router = APIRouter(tags=["chat"])

# ── Context cache (avoid scanning filesystem on every request) ────────────────
_ctx_cache = {"data": None, "ts": 0.0}
_CTX_TTL = 60  # seconds


# ── Filesystem helpers ────────────────────────────────────────────────────────

def _scan_directory(mr: str, subpath: str = "", max_items: int = 50) -> list:
    """Scan a directory and return file/folder info."""
    target = os.path.join(mr, subpath) if subpath else mr
    items = []
    try:
        with os.scandir(target) as entries:
            for e in entries:
                try:
                    stat = e.stat()
                    items.append({
                        "name": e.name,
                        "is_dir": e.is_dir(),
                        "size": stat.st_size if not e.is_dir() else 0,
                        "modified": stat.st_mtime,
                    })
                except OSError:
                    pass
    except Exception:
        pass
    items.sort(key=lambda x: (not x["is_dir"], x["name"].lower()))
    return items[:max_items]


def _get_recent_files(mr: str, days: int = 30, limit: int = 50) -> list:
    """Get recently modified media files."""
    cutoff = time.time() - (days * 86400)
    media_exts = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".m4v", ".flv", ".wmv",
                  ".mp3", ".flac", ".wav", ".aac", ".jpg", ".jpeg", ".png"}
    items = []
    try:
        for root, dirs, fnames in os.walk(mr):
            for fname in fnames:
                ext = os.path.splitext(fname)[1].lower()
                if ext not in media_exts:
                    continue
                fpath = os.path.join(root, fname)
                try:
                    st = os.stat(fpath)
                    if st.st_mtime >= cutoff:
                        rel = os.path.relpath(fpath, mr)
                        items.append({
                            "name": fname,
                            "path": rel,
                            "size": st.st_size,
                            "modified": st.st_mtime,
                        })
                except OSError:
                    pass
            if len(items) >= limit * 3:
                break
    except Exception:
        pass
    items.sort(key=lambda x: x["modified"], reverse=True)
    return items[:limit]


def _get_library_stats(mr: str) -> dict:
    """Get quick library statistics."""
    stats = {
        "total_files": 0, "total_dirs": 0,
        "by_type": {"video": 0, "audio": 0, "image": 0, "other": 0},
        "total_size": 0,
        "top_dirs": [],
    }
    media_exts = {
        "video": {".mp4", ".mkv", ".avi", ".mov", ".webm", ".m4v", ".flv", ".wmv", ".ogv"},
        "audio": {".mp3", ".flac", ".wav", ".aac", ".ogg", ".m4a"},
        "image": {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"},
    }
    try:
        with os.scandir(mr) as entries:
            dirs = []
            for e in entries:
                try:
                    if e.is_dir():
                        dirs.append(e.name)
                        stats["total_dirs"] += 1
                    else:
                        stats["total_files"] += 1
                        ext = os.path.splitext(e.name)[1].lower()
                        for ftype, exts in media_exts.items():
                            if ext in exts:
                                stats["by_type"][ftype] += 1
                                break
                        else:
                            stats["by_type"]["other"] += 1
                        try:
                            stats["total_size"] += e.stat().st_size
                        except OSError:
                            pass
                except OSError:
                    pass
            stats["top_dirs"] = sorted(dirs)[:20]
    except Exception:
        pass
    return stats


# ── Context building ──────────────────────────────────────────────────────────

async def _build_chat_context() -> dict:
    """Gather comprehensive library context for the AI. Cached for 60s."""
    now = time.time()
    if _ctx_cache["data"] and (now - _ctx_cache["ts"]) < _CTX_TTL:
        return _ctx_cache["data"]

    mr = settings.media_root
    cat_counts = {}
    catalog_total = 0
    catalog_movies = 0
    catalog_series = 0

    # Database context
    try:
        from app.database import async_session
        from app.models.file_category import FileCategory
        from app.models.download_catalog import DownloadCatalog
        from sqlalchemy import select, func
        async with async_session() as db:
            cat_result = await db.execute(
                select(FileCategory.category, func.count(FileCategory.file_path))
                .group_by(FileCategory.category)
            )
            cat_counts = {r[0]: r[1] for r in cat_result.all()}
            catalog_total = (await db.execute(select(func.count(DownloadCatalog.id)))).scalar() or 0
            catalog_movies = (await db.execute(select(func.count(DownloadCatalog.id)).where(DownloadCatalog.title_type == "movie"))).scalar() or 0
            catalog_series = (await db.execute(select(func.count(DownloadCatalog.id)).where(DownloadCatalog.title_type.in_(["series", "tv_series"])))).scalar() or 0
    except Exception:
        pass

    # Filesystem context
    stats = _get_library_stats(mr)
    recent = _get_recent_files(mr, days=30, limit=20)
    top_dirs = _scan_directory(mr, max_items=30)

    ctx = {
        "mr": mr,
        "catalog_total": catalog_total,
        "catalog_movies": catalog_movies,
        "catalog_series": catalog_series,
        "cat_counts": cat_counts,
        "stats": stats,
        "recent_files": recent,
        "top_level": top_dirs,
    }

    # Cache for next request
    _ctx_cache["data"] = ctx
    _ctx_cache["ts"] = time.time()
    return ctx


def _build_system_prompt(ctx: dict) -> str:
    """Build a comprehensive system prompt with full library context."""
    stats = ctx["stats"]
    size_str = _fmt_size(stats["total_size"])

    # Build recent files list
    recent_lines = []
    for f in ctx["recent_files"][:15]:
        date_str = time.strftime("%Y-%m-%d", time.localtime(f["modified"]))
        recent_lines.append(f"  {date_str}  {f['name']}  ({_fmt_size(f['size'])})")
    recent_str = "\n".join(recent_lines) if recent_lines else "  (none)"

    # Build directory listing
    dir_lines = []
    for item in ctx["top_level"][:20]:
        if item["is_dir"]:
            dir_lines.append(f"  {item['name']}/")
        else:
            dir_lines.append(f"  {item['name']}  ({_fmt_size(item['size'])})")
    dir_str = "\n".join(dir_lines) if dir_lines else "  (empty)"

    return f"""You are a fun, witty, and knowledgeable AI assistant for a media server. You have REAL-TIME access to the file system and database.

## Your Personality
- You're enthusiastic about movies, TV shows, and music
- You have strong opinions about media — don't be afraid to give genuine recommendations
- You use casual, friendly language — like talking to a friend who's also a film nerd
- You can use emojis sparingly but naturally (not every message)
- You're helpful but also entertaining — make the conversation fun
- You remember what we've talked about in this conversation
- If someone says something playful like "heyy" or uses ":3", match their energy
- You have a slight幽默感 (sense of humor) — occasional witty remarks are welcome
- You're honest — if something in the library looks bad, you can say so gently

## Your Capabilities
- Browse any directory on the server
- Search for files by name, type, or date
- View file metadata (size, date, codec info)
- Suggest clean filenames for messy media files
- Recommend media based on the library
- Help organize and manage the media collection

## Current Library State

**Location:** {ctx['mr']}

**Collection:**
- {stats['total_files']} files across {stats['total_dirs']} directories
- Total size: {size_str}
- Video files: {stats['by_type']['video']}
- Audio files: {stats['by_type']['audio']}
- Image files: {stats['by_type']['image']}

**Catalog:** {ctx['catalog_total']} entries ({ctx['catalog_movies']} movies, {ctx['catalog_series']} series)
**Categories:** {json.dumps(ctx['cat_counts']) if ctx['cat_counts'] else 'not yet categorized'}

**Top-Level Contents:**
{dir_str}

**Recently Added (last 30 days):**
{recent_str}

## Response Guidelines
- Format responses nicely with bullet points, numbered lists, or tables when appropriate
- Use bold for filenames and key information
- Include file sizes and dates when listing files
- Group results logically (by type, date, size)
- For filenames, show the original AND the suggested clean name side by side
- Be concise but thorough
- Respond in the same language as the user
- Use markdown-style formatting for readability
- Keep the vibe friendly and engaging"""


def _fmt_size(b: int) -> str:
    """Format bytes to human-readable size."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if b < 1024:
            return f"{b:.1f} {unit}"
        b /= 1024
    return f"{b:.1f} PB"


# ── AI routing ────────────────────────────────────────────────────────────────

async def _ai_chat(messages: list, temperature: float = 0.7, max_tokens: int = 2048) -> str:
    """Try Agnes AI first, fall back to local llama-server."""
    result = await agnes_ai.chat(messages, temperature=temperature, max_tokens=max_tokens)
    if result:
        return result

    logger.info("Agnes AI unavailable — trying local AI fallback")
    from app.services import local_ai
    local_result = await local_ai._call_llm(
        system=messages[0]["content"] if messages else "",
        user=messages[-1]["content"] if messages else "",
        max_tokens=max_tokens,
        temperature=temperature,
    )
    if local_result:
        return local_result

    return "AI unavailable — both Agnes AI and local AI are unreachable."


async def _ai_chat_stream(messages: list, request: Request, temperature: float = 0.7, max_tokens: int = 2048):
    """Stream AI response. Yields SSE-formatted chunks."""
    # 1. Try Agnes AI streaming
    agnes_ok = False
    try:
        async for chunk in agnes_ai.chat_stream(messages, temperature=temperature, max_tokens=max_tokens):
            if await request.is_disconnected():
                return
            # Check if chunk is an error JSON
            if chunk.startswith("{") and chunk.endswith("}"):
                try:
                    err = json.loads(chunk)
                    if "error" in err:
                        logger.warning("Agnes stream error: %s", err["error"])
                        break
                except json.JSONDecodeError:
                    pass
            agnes_ok = True
            yield f"data: {json.dumps({'delta': chunk})}\n\n"
        if agnes_ok:
            return  # Agnes completed successfully
    except Exception as e:
        logger.warning("Agnes AI stream failed: %s", e)

    # 2. Fallback: local AI streaming
    logger.info("Trying local AI fallback")
    from app.services import local_ai
    import httpx

    if not await local_ai.ensure_running():
        yield f"data: {json.dumps({'delta': '*AI unavailable.* Both cloud and local AI are unreachable.'})}\n\n"
        return

    local_url = f"{settings.local_ai_url}/v1/chat/completions"
    payload = {
        "model": settings.local_ai_model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": True,
    }

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream("POST", local_url, json=payload) as r:
                if r.status_code != 200:
                    yield f"data: {json.dumps({'delta': f'*Local AI error: HTTP {r.status_code}*'})}\n\n"
                    return
                async for line in r.aiter_lines():
                    if await request.is_disconnected():
                        return
                    line = line.strip()
                    if not line or not line.startswith("data: "):
                        continue
                    data_str = line[6:]
                    if data_str == "[DONE]":
                        continue
                    try:
                        data = json.loads(data_str)
                        delta = data.get("choices", [{}])[0].get("delta", {}).get("content", "")
                        if delta:
                            yield f"data: {json.dumps({'delta': delta})}\n\n"
                    except json.JSONDecodeError:
                        pass
    except Exception as e:
        yield f"data: {json.dumps({'delta': f'*Local AI error: {e}*'})}\n\n"


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/api/chat/stream")
async def chat_stream(request: Request):
    """SSE endpoint for streaming chat responses."""
    message = request.query_params.get("message", "")
    history_json = request.query_params.get("history", "[]")

    if not message:
        async def empty_gen():
            yield f"data: {json.dumps({'delta': 'Please say something!'})}\n\n"
        return StreamingResponse(empty_gen(), media_type="text/event-stream")

    ctx = await _build_chat_context()
    system_prompt = _build_system_prompt(ctx)

    history = json.loads(history_json)
    messages = [{"role": "system", "content": system_prompt}]
    for h in history[-10:]:
        messages.append({"role": h.get("role", "user"), "content": h.get("content", "")})
    messages.append({"role": "user", "content": message})

    async def generate():
        try:
            async for chunk in _ai_chat_stream(messages, request):
                yield chunk
        except Exception as e:
            logger.warning("Chat stream error: %s", e)
            yield f"data: {json.dumps({'delta': f'Server error: {e}'})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.post("/api/chat")
async def chat_with_ai(payload: dict):
    """Non-streaming chat endpoint (fallback)."""
    message = (payload.get("message") or "").strip()
    history = payload.get("history") or []
    if not message:
        return {"response": "Please say something!"}

    ctx = await _build_chat_context()
    system_prompt = _build_system_prompt(ctx)

    messages = [{"role": "system", "content": system_prompt}]
    for h in history[-10:]:
        messages.append({"role": h["role"], "content": h["content"]})
    messages.append({"role": "user", "content": message})

    response = await _ai_chat(messages, temperature=0.7, max_tokens=2048)
    return {"response": response}


@router.get("/api/ai-rename-suggest")
async def ai_rename_suggest(filename: str = ""):
    if not filename:
        return {"suggestion": filename}

    system = (
        "You are a file renaming assistant. Given a messy media filename, suggest a clean, organized replacement.\n"
        "Rules:\n"
        "- For movies: 'Title (Year).ext'\n"
        "- For TV series: 'Title - S01E01.ext'\n"
        "- Remove: release group names, codec tags (x264, x265, 10bit), source (BluRay, WEB-DL, HDRip), resolution (720p, 1080p, 4K)\n"
        "- Keep the original extension\n"
        "- Return ONLY the new filename, nothing else."
    )

    cat_context = ""
    try:
        from app.database import async_session
        from app.models.file_category import FileCategory
        from sqlalchemy import select
        async with async_session() as db:
            cat_result = await db.execute(
                select(FileCategory).where(FileCategory.file_path.like(f"%{filename.split('.')[0]}%"))
            )
            cat = cat_result.scalar_one_or_none()
            if cat:
                cat_context = f"\nDetected category: {cat.category}, year: {cat.year}"
    except Exception:
        pass

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": f"Current filename: {filename}{cat_context}"},
    ]
    result = await _ai_chat(messages, temperature=0.1, max_tokens=64)

    if result.startswith("*") or result.startswith("[Local AI]"):
        return {"suggestion": filename, "error": result}
    return {"suggestion": result}


async def close_ai_clients():
    """Close all AI clients on shutdown."""
    agnes_ai.clear_cache()
    from app.services import local_ai
    await local_ai.stop_server()
