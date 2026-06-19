"""OpenSubtitles.com API integration for automatic subtitle fetching.

Provides subtitle search and download via opensubtitles.com.
Used in addition to (and before) the sub-plus.ir / subzone.ir scrapers.

Rate limit: 100 downloads/day on free tier.
"""
import asyncio
import logging
import time
from typing import Optional, Dict, List
import httpx

from app.config import settings

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 15.0
CACHE_TTL = 60 * 60  # 1 hour
_cache: Dict[str, tuple] = {}
_CACHE_MAX = 300
_token = ""
_token_expires = 0
BASE_URL = "https://api.opensubtitles.com/api/v1"
_DAILY_LIMIT = 100
_daily_used = 0
_daily_reset = 0  # timestamp when the limit resets


def is_configured() -> bool:
    result = bool(settings.opensubtitles_api_key) and bool(settings.opensubtitles_username) and bool(settings.opensubtitles_password)
    logger.debug(f"OpenSubtitles is_configured: {result}")
    return result


async def _login() -> bool:
    """Authenticate and get a bearer token (valid 24h)."""
    global _token, _token_expires
    now = time.time()
    if _token and _token_expires > now + 60:
        logger.debug(f"OpenSubtitles using cached token (expires in {_token_expires - now:.0f}s)")
        return True
    logger.debug("OpenSubtitles attempting login...")
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            r = await client.post(
                f"{BASE_URL}/login",
                json={
                    "username": settings.opensubtitles_username,
                    "password": settings.opensubtitles_password,
                },
            )
            if r.status_code != 200:
                logger.warning(f"OpenSubtitles login failed (HTTP {r.status_code})")
                return False
            data = r.json()
            _token = data.get("token", "")
            _token_expires = now + 86400
            logger.debug(f"OpenSubtitles login success, token expires in 86400s")
            return bool(_token)
    except Exception as e:
        logger.warning(f"OpenSubtitles login error: {e}")
        return False


def _check_rate_limit() -> bool:
    """Return True if we can make a download request today."""
    global _daily_reset, _daily_used
    now = time.time()
    if now > _daily_reset:
        if _daily_used > 0:
            logger.debug(f"OpenSubtitles rate limit reset: was {_daily_used}/{_DAILY_LIMIT}, now 0")
        _daily_used = 0
        _daily_reset = now + 86400
    ok = _daily_used < _DAILY_LIMIT
    if not ok:
        logger.warning(f"OpenSubtitles rate limit reached: {_daily_used}/{_DAILY_LIMIT} used")
    else:
        logger.debug(f"OpenSubtitles rate limit check: {_daily_used}/{_DAILY_LIMIT} used, ok={ok}")
    return ok


async def _request(method: str, path: str, json_data: dict = None) -> Optional[dict]:
    """Make an authenticated OpenSubtitles API request."""
    if not await _login():
        return None
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            headers = {
                "Authorization": f"Bearer {_token}",
                "Content-Type": "application/json",
                "Api-Key": settings.opensubtitles_api_key,
            }
            url = f"{BASE_URL}{path}"
            t0 = asyncio.get_event_loop().time()
            logger.debug(f"OpenSubtitles _request: {method} {path}")
            if method == "GET":
                r = await client.get(url, headers=headers, params=json_data)
            else:
                r = await client.post(url, headers=headers, json=json_data)
            elapsed = asyncio.get_event_loop().time() - t0
            logger.debug(f"OpenSubtitles _request: {method} {path} -> HTTP {r.status_code} in {elapsed:.2f}s")
            if r.status_code == 401:
                logger.warning(f"OpenSubtitles 401 unauthorized on {path}, clearing token")
                _token = ""
                _token_expires = 0
                return None
            if r.status_code != 200:
                logger.warning(f"OpenSubtitles non-200 status {r.status_code} on {path}")
                return None
            return r.json()
    except Exception as e:
        logger.warning(f"OpenSubtitles request error on {path}: {e}")
        return None


async def search(query: str, imdb_id: str = "", languages: list = None, season: int = 0, episode: int = 0) -> list:
    """Search for subtitles by query or IMDB id.
    Returns list of {id, name, language, format, rating, downloads, url, files}.
    """
    if not is_configured():
        logger.debug("OpenSubtitles search skipped: not configured")
        return []
    params = {}
    if imdb_id:
        params["imdb_id"] = imdb_id.replace("tt", "")
    if query:
        params["query"] = query
    if languages:
        params["languages"] = ",".join(languages)
    else:
        params["languages"] = "en,fa"
    if season > 0:
        params["season_number"] = season
    if episode > 0:
        params["episode_number"] = episode
    logger.debug(f"OpenSubtitles search: query={query!r} imdb_id={imdb_id!r} languages={params.get('languages')} season={season} episode={episode}")
    data = await _request("GET", "/subtitles", params)
    if not data:
        logger.debug("OpenSubtitles search returned no data")
        return []
    results = []
    for item in (data.get("data") or []):
        attrs = item.get("attributes", {})
        files_data = attrs.get("files", [])
        results.append({
            "id": item.get("id"),
            "name": attrs.get("subtitle_id"),
            "language": attrs.get("language"),
            "language_code": attrs.get("language_code"),
            "format": attrs.get("format"),
            "rating": attrs.get("ratings", 0),
            "downloads": attrs.get("download_count", 0),
            "files": [{"id": f.get("file_id"), "name": f.get("file_name")} for f in files_data],
        })
    logger.debug(f"OpenSubtitles search returned {len(results)} results")
    return results


async def download(file_id: int) -> Optional[bytes]:
    """Download subtitle file content by file_id. Returns raw bytes or None.
    Respects the 100/day rate limit.
    """
    global _daily_used
    logger.debug(f"OpenSubtitles download start: file_id={file_id}")
    if not _check_rate_limit():
        logger.warning(f"OpenSubtitles daily rate limit reached (100/day), download skipped for file_id={file_id}")
        return None
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            headers = {
                "Authorization": f"Bearer {_token}",
                "Content-Type": "application/json",
            }
            r = await client.get(
                f"{BASE_URL}/download",
                headers=headers,
                params={"file_id": file_id},
            )
            if r.status_code != 200:
                logger.warning(f"OpenSubtitles download file_id={file_id} -> HTTP {r.status_code}, no link obtained")
                return None
            data = r.json()
            link = data.get("link")
            if not link:
                logger.warning(f"OpenSubtitles download file_id={file_id}: no link in response")
                return None
            logger.debug(f"OpenSubtitles download file_id={file_id}: got download link, fetching content...")
            dl = await client.get(link, timeout=15.0)
            if dl.status_code == 200:
                _daily_used += 1
                logger.debug(f"OpenSubtitles download file_id={file_id}: success, {len(dl.content)} bytes (daily used: {_daily_used})")
                return dl.content
            logger.warning(f"OpenSubtitles download file_id={file_id}: content fetch returned HTTP {dl.status_code}")
            return None
    except Exception as e:
        logger.warning(f"OpenSubtitles download error for file_id={file_id}: {e}")
        return None
