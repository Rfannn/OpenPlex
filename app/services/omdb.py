import logging
import time
from typing import Optional, Dict, Any
import httpx

from app.config import settings

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 15.0
CACHE_TTL = 60 * 60 * 6  # 6 hours
_cache: Dict[str, tuple] = {}
_CACHE_MAX = 500


def is_configured() -> bool:
    configured = bool(settings.omdb_api_key)
    logger.debug(f"OMDb is_configured={configured}")
    return configured


def _evict_oldest():
    from app.services.cache import evict_oldest
    evict_oldest(_cache, _CACHE_MAX)


async def _request(params: dict) -> Optional[dict]:
    """Make an OMDb API request. Returns parsed JSON or None."""
    if not is_configured():
        logger.debug("OMDb _request skipped: not configured")
        return None
    params["apikey"] = settings.omdb_api_key
    cache_key = str(sorted(params.items()))
    now = time.time()
    cached = _cache.get(cache_key)
    if cached and (now - cached[0]) < CACHE_TTL:
        logger.debug(f"OMDb _request cache HIT for {params.get('i','') or params.get('s','')}")
        return cached[1]
    url = "https://www.omdbapi.com"
    logger.debug(f"OMDb _request GET {url} params={params}")
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            t0 = time.time()
            r = await client.get(url, params=params)
            dur = time.time() - t0
            logger.debug(f"OMDb _request status={r.status_code} duration={dur:.3f}s")
            if r.status_code != 200:
                logger.warning(f"OMDb _request non-200 status={r.status_code}")
                return None
            data = r.json()
            if data.get("Response") != "True":
                logger.warning(f"OMDb _request API returned Response!=True: {data.get('Error', 'unknown error')}")
                return None
            _cache[cache_key] = (now, data)
            _evict_oldest()
            logger.debug(f"OMDb _request success - cached {len(_cache)} entries")
            return data
    except Exception as e:
        logger.warning(f"OMDb _request exception: {e}")
        return None


async def get_by_imdb(imdb_id: str) -> Optional[dict]:
    """Fetch movie/TV details by IMDB ID from OMDb.
    Returns dict with keys: title, year, genre, director, actors, plot,
    imdb_rating, imdb_votes, ratings (list of {source, value}), runtime_min,
    poster_url, type, awards, metascore, language, country, or None.
    """
    if not imdb_id or not imdb_id.startswith("tt"):
        logger.debug(f"OMDb get_by_imdb invalid imdb_id={imdb_id!r}")
        return None
    logger.debug(f"OMDb get_by_imdb querying imdb_id={imdb_id}")
    data = await _request({"i": imdb_id, "plot": "short"})
    if not data:
        logger.debug(f"OMDb get_by_imdb no result for imdb_id={imdb_id}")
        return None
    runtime_str = (data.get("Runtime") or "").replace(" min", "")
    try:
        runtime_min = int(runtime_str)
    except (ValueError, TypeError):
        runtime_min = 0
    media_type = data.get("Type", "movie")
    ratings = []
    for r in data.get("Ratings", []):
        ratings.append({"source": r.get("Source"), "value": r.get("Value")})
    return {
        "title": data.get("Title"),
        "year": (data.get("Year") or "")[:4],
        "genre": [g.strip() for g in (data.get("Genre") or "").split(",") if g.strip()],
        "director": data.get("Director", ""),
        "actors": [a.strip() for a in (data.get("Actors") or "").split(",") if a.strip()],
        "plot": data.get("Plot", ""),
        "language": data.get("Language", ""),
        "country": data.get("Country", ""),
        "awards": data.get("Awards", ""),
        "imdb_rating": data.get("imdbRating", ""),
        "imdb_votes": data.get("imdbVotes", ""),
        "metascore": data.get("Metascore", ""),
        "ratings": ratings,
        "poster_url": data.get("Poster"),
        "runtime_min": runtime_min,
        "type": media_type,
    }


async def search(query: str, limit: int = 10) -> list:
    """Search OMDb by title. Returns list of {title, year, imdb_id, type, poster_url}."""
    if not query or len(query.strip()) < 2:
        logger.debug(f"OMDb search query too short: {query!r}")
        return []
    logger.debug(f"OMDb search query={query!r} limit={limit}")
    data = await _request({"s": query, "type": "movie"})
    if not data:
        logger.debug(f"OMDb search no results for query={query!r}")
        return []
    results = []
    for r in (data.get("Search") or [])[:limit]:
        results.append({
            "title": r.get("Title"),
            "year": (r.get("Year") or "")[:4],
            "imdb_id": r.get("imdb"),
            "type": r.get("Type", "movie"),
            "poster_url": r.get("Poster"),
        })
    logger.debug(f"OMDb search returning {len(results)} results for query={query!r}")
    return results
