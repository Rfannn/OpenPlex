"""Local AI service — llama-server fallback.

This module manages a local llama-server process that only starts when:
1. Agnes AI is down or rate-limited
2. A user is actively waiting for a response

The process auto-stops after an idle timeout to save resources.
"""
import asyncio
import json
import logging
import os
import signal
import subprocess
import time
from pathlib import Path
from typing import Any, Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

LOCAL_AI_URL = f"{settings.local_ai_url}/v1/chat/completions"
HEALTH_URL = f"{settings.local_ai_url}/health"
TIMEOUT = 120.0

_cache: dict[str, tuple[float, Any]] = {}
CACHE_TTL = 3600

# ── Process management ───────────────────────────────────────────────────────
_process: Optional[subprocess.Popen] = None
_last_used: float = 0.0
_IDLE_TIMEOUT = 300  # 5 minutes — shut down if unused
_start_lock = asyncio.Lock()


async def _is_alive() -> bool:
    """Check if llama-server is responding."""
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.get(HEALTH_URL)
            return r.status_code == 200
    except Exception:
        return False


async def _start_server() -> bool:
    """Start llama-server as a subprocess. Returns True if started successfully."""
    global _process

    if _process is not None and _process.poll() is None:
        return True  # already running

    # Find the model file
    model_path = "/mnt/hdd/models/qwen2.5-3b-instruct-q4_k_m.gguf"
    llama_server = "llama-server"

    # Check common locations
    candidates = [
        llama_server,
        "/usr/local/bin/llama-server",
        str(Path.home() / ".local/bin/llama-server"),
        "/opt/llama.cpp/build/bin/llama-server",
    ]

    server_path = None
    for c in candidates:
        if os.path.exists(c) and os.access(c, os.X_OK):
            server_path = c
            break

    if not server_path:
        logger.warning("llama-server binary not found — cannot start local AI")
        return False

    if not os.path.exists(model_path):
        logger.warning("Model file not found: %s — cannot start local AI", model_path)
        return False

    port = int(settings.local_ai_url.rsplit(":", 1)[-1]) if ":" in settings.local_ai_url else 8081

    try:
        _process = subprocess.Popen(
            [
                server_path,
                "-m", model_path,
                "--host", "127.0.0.1",
                "--port", str(port),
                "-c", "2048",
                "--ctx-size", "2048",
                "-ngl", "99",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            preexec_fn=os.setsid if os.name != "nt" else None,
        )
        logger.info("llama-server started (PID %d)", _process.pid)

        # Wait for server to become ready (up to 30s)
        for _ in range(30):
            await asyncio.sleep(1.0)
            if await _is_alive():
                logger.info("llama-server ready on port %d", port)
                return True
            if _process.poll() is not None:
                logger.error("llama-server exited during startup (rc=%d)", _process.returncode)
                _process = None
                return False

        logger.warning("llama-server startup timed out after 30s")
        return False
    except Exception as e:
        logger.error("Failed to start llama-server: %s", e)
        _process = None
        return False


async def stop_server():
    """Gracefully stop the llama-server process."""
    global _process
    if _process is None:
        return
    if _process.poll() is not None:
        _process = None
        return
    try:
        # Send SIGTERM to process group
        os.killpg(os.getpgid(_process.pid), signal.SIGTERM)
        try:
            _process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(os.getpgid(_process.pid), signal.SIGKILL)
            _process.wait(timeout=2)
        logger.info("llama-server stopped (PID %d)", _process.pid)
    except Exception as e:
        logger.warning("Error stopping llama-server: %s", e)
    finally:
        _process = None


async def ensure_running() -> bool:
    """Ensure llama-server is running. Starts it if needed.

    Uses a lock to prevent multiple concurrent startup attempts.
    """
    global _last_used

    if await _is_alive():
        _last_used = time.time()
        return True

    if not settings.local_ai_auto_start:
        logger.debug("Local AI not running and auto_start is disabled")
        return False

    async with _start_lock:
        # Double-check after acquiring lock
        if await _is_alive():
            _last_used = time.time()
            return True
        return await _start_server()


async def _idle_watcher():
    """Background task that stops llama-server after idle timeout."""
    while True:
        await asyncio.sleep(60)
        if _process is None or _process.poll() is not None:
            continue
        if _last_used > 0 and (time.time() - _last_used) > _IDLE_TIMEOUT:
            logger.info("llama-server idle for %ds — stopping", _IDLE_TIMEOUT)
            await stop_server()


_watcher_started = False


def start_idle_watcher():
    """Start the idle watcher background task (call once at startup)."""
    global _watcher_started
    if _watcher_started:
        return
    _watcher_started = True
    asyncio.create_task(_idle_watcher())
    logger.info("Local AI idle watcher started (timeout=%ds)", _IDLE_TIMEOUT)


# ── LLM calls ────────────────────────────────────────────────────────────────

async def _call_llm(
    system: str,
    user: str,
    max_tokens: int = 256,
    temperature: float = 0.0,
) -> Optional[str]:
    """Call the local LLM. Ensures server is running first."""
    if not await ensure_running():
        return None

    global _last_used
    _last_used = time.time()

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            payload = {
                "model": settings.local_ai_model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "max_tokens": max_tokens,
                "temperature": temperature,
            }
            resp = await client.post(LOCAL_AI_URL, json=payload)
            resp.raise_for_status()
            data = resp.json()
            choice = data["choices"][0]["message"]["content"]
            return choice.strip()
    except httpx.ConnectError:
        logger.warning("Local AI server not reachable")
        return None
    except Exception as e:
        logger.warning("Local AI call failed: %s", e)
        return None


# ── Cache helpers ─────────────────────────────────────────────────────────────

def _cache_key(system: str, user: str) -> str:
    return f"{system}|{user}"


def _get_cached(key: str) -> Optional[Any]:
    entry = _cache.get(key)
    if entry and time.time() - entry[0] < CACHE_TTL:
        return entry[1]
    return None


def _set_cache(key: str, value: Any):
    _cache[key] = (time.time(), value)


def _extract_year(text: str) -> Optional[int]:
    import re
    m = re.search(r"\b(19\d{2}|20\d{2})\b", text)
    return int(m.group(1)) if m else None


# ── Public API ───────────────────────────────────────────────────────────────

async def categorize_media(
    title: str,
    filename: str,
    genre_hints: Optional[list[str]] = None,
) -> dict[str, Any]:
    system = (
        "You are a media categorization AI. Given a media title and filename, "
        "classify it. Return ONLY valid JSON with keys: "
        "category (string: movie/series/anime/other), "
        "genre (array of strings), "
        "year (integer or null), "
        "confidence (float 0-1). "
        "No explanation, no markdown, just JSON."
    )
    hints = f" Genre hints: {', '.join(genre_hints)}" if genre_hints else ""
    user = f"Title: {title}\nFilename: {filename}{hints}"

    ck = _cache_key(system, user)
    cached = _get_cached(ck)
    if cached:
        return cached

    raw = await _call_llm(system, user, max_tokens=128)
    if not raw:
        return {"category": "other", "genre": [], "year": None, "confidence": 0, "error": "local_ai_unreachable"}

    try:
        parsed = json.loads(raw)
        result = {
            "category": parsed.get("category", "other"),
            "genre": parsed.get("genre", []),
            "year": parsed.get("year"),
            "confidence": parsed.get("confidence", 0),
        }
        _set_cache(ck, result)
        return result
    except (json.JSONDecodeError, AttributeError):
        logger.warning("Failed to parse local AI categorize response: %s", raw[:200])
        year = _extract_year(raw)
        return {"category": "other", "genre": [], "year": year, "confidence": 0.3, "error": "parse_fallback"}


async def recommend_media(
    recently_watched: list[str],
    available_titles: list[str],
    max_results: int = 10,
) -> list[dict[str, Any]]:
    system = (
        "You are a media recommendation AI. Given recently watched titles and "
        "available titles, suggest relevant recommendations. "
        "Return ONLY a valid JSON array of objects with keys: "
        "title (string), reason (string), score (float 0-1). "
        f"Maximum {max_results} recommendations. No explanation, no markdown."
    )
    user = (
        f"Recently watched: {json.dumps(recently_watched)}\n"
        f"Available: {json.dumps(available_titles[:20])}"
    )

    ck = _cache_key(system, user)
    cached = _get_cached(ck)
    if cached:
        return cached

    raw = await _call_llm(system, user, max_tokens=512)
    if not raw:
        return []

    try:
        parsed = json.loads(raw)
        result = parsed if isinstance(parsed, list) else []
        _set_cache(ck, result)
        return result
    except (json.JSONDecodeError, AttributeError):
        logger.warning("Failed to parse local AI recommend response: %s", raw[:200])
        return []


async def enrich_metadata(
    title: str,
    filename: str,
    existing_metadata: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    system = (
        "You are a media metadata enrichment AI. Given a title, filename, and "
        "existing metadata, return enhanced metadata as valid JSON with keys: "
        "title (string), year (int or null), genre (array of strings), "
        "synopsis (string), tags (array of strings), "
        "parental_rating (string or null). No explanation, no markdown."
    )
    existing = json.dumps(existing_metadata or {})
    user = f"Title: {title}\nFilename: {filename}\nExisting metadata: {existing}"

    ck = _cache_key(system, user)
    cached = _get_cached(ck)
    if cached:
        return cached

    raw = await _call_llm(system, user, max_tokens=256)
    if not raw:
        return {"title": title, "year": None, "genre": [], "synopsis": "", "tags": [], "parental_rating": None}

    try:
        parsed = json.loads(raw)
        result = {
            "title": parsed.get("title", title),
            "year": parsed.get("year"),
            "genre": parsed.get("genre", []),
            "synopsis": parsed.get("synopsis", ""),
            "tags": parsed.get("tags", []),
            "parental_rating": parsed.get("parental_rating"),
        }
        _set_cache(ck, result)
        return result
    except (json.JSONDecodeError, AttributeError):
        logger.warning("Failed to parse local AI enrich response: %s", raw[:200])
        return {"title": title, "year": None, "genre": [], "synopsis": "", "tags": [], "parental_rating": None}


async def search_metadata(query: str) -> Optional[dict[str, Any]]:
    system = (
        "You are a media search AI. Given a search query, return metadata for "
        "the most likely media match. Return ONLY valid JSON with keys: "
        "title (string), year (int or null), genre (array of strings), "
        "synopsis (string), imdb_id (string or null), "
        "media_type (string: movie/tv). No explanation, no markdown."
    )
    user = f"Search query: {query}"

    ck = _cache_key(system, user)
    cached = _get_cached(ck)
    if cached:
        return cached

    raw = await _call_llm(system, user, max_tokens=256)
    if not raw:
        return None

    try:
        parsed = json.loads(raw)
        result = {
            "title": parsed.get("title", query),
            "year": parsed.get("year"),
            "genre": parsed.get("genre", []),
            "synopsis": parsed.get("synopsis", ""),
            "imdb_id": parsed.get("imdb_id"),
            "media_type": parsed.get("media_type", "movie"),
            "source": "local_ai",
        }
        _set_cache(ck, result)
        return result
    except (json.JSONDecodeError, AttributeError):
        logger.warning("Failed to parse local AI search_metadata response: %s", raw[:200])
        return None
