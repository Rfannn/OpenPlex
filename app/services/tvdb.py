import logging
import time
from typing import Optional, Dict, List, Any
import httpx

from app.config import settings

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 15.0
CACHE_TTL = 60 * 60 * 6  # 6 hours
_cache: Dict[str, tuple] = {}
_CACHE_MAX = 500
_token = ""
_token_expires = 0
BASE_URL = "https://api4.thetvdb.com/v4"


def is_configured() -> bool:
    result = bool(settings.tvdb_api_key)
    logger.debug(f"TVDb is_configured: {result}")
    return result


async def _login() -> bool:
    """Authenticate with TVDb and get a JWT token."""
    global _token, _token_expires
    now = time.time()
    if _token and _token_expires > now + 60:
        logger.debug("TVDb _login: using cached token (valid until expiry)")
        return True
    logger.debug("TVDb _login: attempting new login...")
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            r = await client.post(
                f"{BASE_URL}/login",
                json={"apikey": settings.tvdb_api_key},
            )
            if r.status_code != 200:
                logger.warning(f"TVDb _login: failed with status {r.status_code}")
                return False
            data = r.json()
            _token = data.get("data", {}).get("token", "")
            _token_expires = now + 86400  # tokens last 24h
            success = bool(_token)
            logger.debug(f"TVDb _login: success={success}, token_expires={_token_expires} ({_token_expires - now}s from now)")
            return success
    except Exception as e:
        logger.warning(f"TVDb _login error: {e}")
        return False


def _evict_oldest():
    from app.services.cache import evict_oldest
    evict_oldest(_cache, _CACHE_MAX)


async def _request(path: str) -> Optional[dict]:
    """Make an authenticated TVDb API request. Returns parsed JSON or None."""
    if not is_configured():
        logger.warning("TVDb _request: not configured, skipping request")
        return None
    if not await _login():
        logger.warning("TVDb _request: login failed for path=%s", path)
        return None
    cache_key = path
    now = time.time()
    cached = _cache.get(cache_key)
    if cached and (now - cached[0]) < CACHE_TTL:
        logger.debug(f"TVDb _request: cache HIT for {path}")
        return cached[1]
    logger.debug(f"TVDb _request: GET {BASE_URL}{path}")
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            start = time.time()
            r = await client.get(
                f"{BASE_URL}{path}",
                headers={"Authorization": f"Bearer {_token}"},
            )
            duration = time.time() - start
            if r.status_code == 401:
                logger.warning(f"TVDb _request: 401 Unauthorized for {path}, clearing token")
                _token = ""
                _token_expires = 0
                return None
            if r.status_code != 200:
                logger.warning(f"TVDb _request: {r.status_code} for {path} (duration={duration:.2f}s)")
                return None
            logger.debug(f"TVDb _request: {r.status_code} for {path} (duration={duration:.2f}s)")
            data = r.json()
            _cache[cache_key] = (now, data)
            _evict_oldest()
            return data.get("data")
    except Exception as e:
        logger.warning(f"TVDb _request error for {path}: {e}")
        return None


async def search(query: str, limit: int = 10) -> list:
    """Search TVDb by title. Returns list of {id, name, year, imdb_id, overview, image_url}."""
    logger.debug(f"TVDb search: query='{query}', limit={limit}")
    if not query or len(query.strip()) < 2:
        logger.debug("TVDb search: query too short, returning empty list")
        return []
    import urllib.parse
    data = await _request(f"/search?query={urllib.parse.quote(query)}&limit={limit}&type=series")
    if not data:
        logger.debug(f"TVDb search: no data returned for query='{query}'")
        return []
    results = []
    for r in (data if isinstance(data, list) else []):
        results.append({
            "id": r.get("id"),
            "name": r.get("name"),
            "year": (r.get("first_air_time") or "")[:4],
            "imdb_id": r.get("imdbId"),
            "overview": r.get("overview"),
            "image_url": r.get("image"),
        })
    logger.debug(f"TVDb search: query='{query}' returned {len(results)} results")
    return results


async def get_series_episodes(tvdb_id: int, season: str = "") -> list:
    """Get episode list for a series from TVDb.
    Returns list of {id, name, episode_number, season_number, air_date, overview, image_url}.
    """
    params = "" if not season else f"?season={season}"
    logger.debug(f"TVDb get_series_episodes: tvdb_id={tvdb_id}, season='{season}'")
    data = await _request(f"/series/{tvdb_id}/episodes/default{params}")
    if not data:
        logger.debug(f"TVDb get_series_episodes: no data for tvdb_id={tvdb_id}, season='{season}'")
        return []
    episodes = data.get("episodes") if isinstance(data, dict) else data
    if not isinstance(episodes, list):
        logger.warning(f"TVDb get_series_episodes: unexpected data format for tvdb_id={tvdb_id}")
        return []
    results = []
    for e in episodes:
        results.append({
            "id": e.get("id"),
            "name": e.get("name"),
            "episode_number": e.get("number"),
            "season_number": e.get("seasonNumber"),
            "air_date": (e.get("airDate") or ""),
            "overview": e.get("overview"),
            "image_url": e.get("image"),
        })
    logger.debug(f"TVDb get_series_episodes: tvdb_id={tvdb_id}, season='{season}' -> {len(results)} episodes")
    return results


async def get_series_seasons(tvdb_id: int) -> list:
    """Get season list for a series. Returns list of {id, number, name, image_url}."""
    logger.debug(f"TVDb get_series_seasons: tvdb_id={tvdb_id}")
    data = await _request(f"/series/{tvdb_id}/seasons")
    if not data:
        logger.debug(f"TVDb get_series_seasons: no data for tvdb_id={tvdb_id}")
        return []
    if not isinstance(data, list):
        logger.warning(f"TVDb get_series_seasons: unexpected data format for tvdb_id={tvdb_id}")
        return []
    results = []
    for s in data:
        results.append({
            "id": s.get("id"),
            "number": s.get("number"),
            "name": s.get("name"),
            "image_url": s.get("image"),
        })
    logger.debug(f"TVDb get_series_seasons: tvdb_id={tvdb_id} -> {len(results)} seasons")
    return results


async def get_series_artwork(tvdb_id: int) -> list:
    """Get artwork for a series. Returns list of {url, type, likes}."""
    logger.debug(f"TVDb get_series_artwork: tvdb_id={tvdb_id}")
    data = await _request(f"/series/{tvdb_id}/artworks")
    if not data:
        logger.debug(f"TVDb get_series_artwork: no data for tvdb_id={tvdb_id}")
        return []
    if not isinstance(data, list):
        logger.warning(f"TVDb get_series_artwork: unexpected data format for tvdb_id={tvdb_id}")
        return []
    results = []
    for a in data:
        results.append({
            "url": a.get("image"),
            "type": a.get("type", ""),
            "score": a.get("score", 0),
        })
    logger.debug(f"TVDb get_series_artwork: tvdb_id={tvdb_id} -> {len(results)} artworks")
    return results
