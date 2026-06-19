import logging
import time
from typing import Optional, Dict, List, Any
import httpx

from app.config import settings

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 3.0
CACHE_TTL = 60 * 60 * 6  # 6 hours
_cache: Dict[str, tuple] = {}
_CACHE_MAX = 500

# Global circuit breaker — if Fanart is unreachable, skip all requests for a cooldown
_last_failure: float = 0.0
_BREAKER_COOLDOWN = 300.0  # 5 minutes


def _circuit_open() -> bool:
    global _last_failure
    if _last_failure == 0:
        return False
    elapsed = time.time() - _last_failure
    if elapsed < _BREAKER_COOLDOWN:
        return True
    _last_failure = 0  # reset after cooldown expires
    return False


def is_configured() -> bool:
    result = bool(settings.fanart_api_key)
    logger.debug("Fanart.tv is_configured=%s", result)
    return result


def _evict_oldest():
    from app.services.cache import evict_oldest
    evict_oldest(_cache, _CACHE_MAX)


async def _request(path: str) -> Optional[dict]:
    """Make a Fanart.tv API request. Returns parsed JSON or None."""
    if not is_configured():
        logger.debug("Fanart.tv _request skipped — not configured (path=%s)", path)
        return None
    if _circuit_open():
        logger.debug("Fanart.tv _request skipped — circuit breaker open for path=%s", path)
        return None
    cache_key = path
    now = time.time()
    cached = _cache.get(cache_key)
    if cached and (now - cached[0]) < CACHE_TTL:
        logger.debug("Fanart.tv cache hit for %s", path)
        return cached[1]
    logger.debug("Fanart.tv _request method=GET path=%s", path)
    try:
        url = f"https://webservice.fanart.tv/v3/{path}"
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            t0 = time.time()
            r = await client.get(url, params={"api_key": settings.fanart_api_key})
            duration = time.time() - t0
            logger.debug("Fanart.tv _request status=%s duration=%.3fs path=%s", r.status_code, duration, path)
            if r.status_code != 200:
                logger.warning("Fanart.tv _request non-200 status=%s path=%s", r.status_code, path)
                return None
            data = r.json()
            _cache[cache_key] = (now, data)
            _evict_oldest()
            logger.debug("Fanart.tv _request success path=%s keys=%s", path, list(data.keys()))
            return data
    except Exception as e:
        logger.warning("Fanart.tv _request exception for %s: %s (%s)", path, e, type(e).__name__)
        global _last_failure
        _last_failure = time.time()
        return None


async def get_movie_images(imdb_id: str) -> dict:
    """Fetch high-res movie artwork from Fanart.tv.
    Returns dict with keys: hdmovielogo, moviebackground, movieposter,
    moviedisc, movielogo, moviebanner, moviethumb — each a list of {url, likes}.
    Returns empty dict on failure.
    """
    if not imdb_id or not imdb_id.startswith("tt"):
        logger.debug("Fanart.tv get_movie_images skipped — invalid imdb_id=%s", imdb_id)
        return {}
    data = await _request(f"movies/{imdb_id}")
    if not data:
        logger.debug("Fanart.tv get_movie_images no data for imdb_id=%s", imdb_id)
        return {}
    out = {}
    for key in ("hdmovielogo", "moviebackground", "movieposter", "moviedisc", "movielogo", "moviebanner", "moviethumb"):
        items = data.get(key, [])
        if items:
            out[key] = [{"url": i.get("url"), "likes": i.get("likes", 0)} for i in items]
    logger.debug("Fanart.tv get_movie_images imdb_id=%s returned %d image groups", imdb_id, len(out))
    return out


async def get_tv_images(tvdb_id: int) -> dict:
    """Fetch high-res TV artwork from Fanart.tv by TVDb id.
    Returns dict with keys: hdtvlogo, tvbackground, tvposter, tvthumb,
    showbackground, tvbanner — each a list of {url, likes}.
    Returns empty dict on failure.
    """
    if not tvdb_id:
        logger.debug("Fanart.tv get_tv_images skipped — tvdb_id is falsy")
        return {}
    data = await _request(f"tv/{tvdb_id}")
    if not data:
        logger.debug("Fanart.tv get_tv_images no data for tvdb_id=%s", tvdb_id)
        return {}
    out = {}
    for key in ("hdtvlogo", "tvbackground", "tvposter", "tvthumb", "showbackground", "tvbanner"):
        items = data.get(key, [])
        if items:
            out[key] = [{"url": i.get("url"), "likes": i.get("likes", 0)} for i in items]
    logger.debug("Fanart.tv get_tv_images tvdb_id=%s returned %d image groups", tvdb_id, len(out))
    return out


def pick_best(items: list) -> Optional[str]:
    """Pick the highest-liked item URL from a fanart list."""
    if not items:
        return None
    best = max(items, key=lambda x: x.get("likes", 0))
    return best.get("url")


async def get_best_backdrop(imdb_id: str) -> Optional[str]:
    """Get the best high-res backdrop for a movie by IMDB id."""
    images = await get_movie_images(imdb_id)
    if not images:
        logger.debug("Fanart.tv get_best_backdrop type=movie imdb_id=%s backdrop_found=False (no images)", imdb_id)
        return None
    backdrop = pick_best(images.get("moviebackground"))
    logger.debug("Fanart.tv get_best_backdrop type=movie imdb_id=%s backdrop_found=%s", imdb_id, backdrop is not None)
    return backdrop


async def get_best_poster(imdb_id: str) -> Optional[str]:
    """Get the best high-res poster for a movie by IMDB id."""
    images = await get_movie_images(imdb_id)
    if not images:
        logger.debug("Fanart.tv get_best_poster type=movie imdb_id=%s poster_found=False (no images)", imdb_id)
        return None
    poster = pick_best(images.get("movieposter"))
    logger.debug("Fanart.tv get_best_poster type=movie imdb_id=%s poster_found=%s", imdb_id, poster is not None)
    return poster
