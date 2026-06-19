"""TMDB (themoviedb.org) integration.

Provides metadata enrichment for catalog entries using their IMDB id.
Used as a fallback when MajidAPI / AzFilm data is missing or incomplete.

The service is OPT-IN: if no TMDB_API_KEY is configured, every call
short-circuits and returns None. This matches the existing pattern
used by `metadata_enricher.py` and `ai_service.py`.
"""
import asyncio
import logging
import time
from typing import Optional, Dict, List, Any
import httpx

from app.config import settings

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 3.0  # network DNS-hijacks TMDB → fail fast
CONSECUTIVE_FAIL_LIMIT = 1  # fail fast — disable after first connection error
CACHE_TTL = 60 * 60 * 6  # 6 hours
_cache: Dict[str, tuple] = {}
_CACHE_MAX = 500
_auth_bad = False
_network_bad = False  # fail-fast flag: set on first connect/timeout error
_consecutive_fails = 0
_last_fail_time = 0.0
_FAIL_COOLDOWN = 300  # 5 min cooldown after network goes bad


def is_configured() -> bool:
    result = bool(settings.tmdb_api_key)
    logger.debug("TMDB is_configured() -> %s", result)
    return result


def _evict_oldest():
    from app.services.cache import evict_oldest
    evict_oldest(_cache, _CACHE_MAX)


async def _request(path: str, params: Optional[dict] = None) -> Optional[dict]:
    """Make an authenticated TMDB API request. Returns parsed JSON or None."""
    global _auth_bad, _network_bad, _last_fail_time, _consecutive_fails
    if not is_configured() or _auth_bad:
        return None
    now = time.time()
    # Fail-fast: if the network is known bad and still in cooldown, bail immediately
    if _network_bad and (now - _last_fail_time) < _FAIL_COOLDOWN:
        return None
    # After cooldown expires, allow retry
    if _network_bad:
        _network_bad = False
        # reset_auth_badge() also resets this
    if params is None:
        params = {}
    params["api_key"] = settings.tmdb_api_key
    cache_key = f"{path}?{tuple(sorted(params.items()))}"
    cached = _cache.get(cache_key)
    if cached and (now - cached[0]) < CACHE_TTL:
        return cached[1]
    t0 = time.time()
    url = f"{settings.tmdb_base_url}{path}"
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            logger.debug("TMDB _request attempting GET %s timeout=%.1fs", url, REQUEST_TIMEOUT)
            r = await client.get(url, params=params)
            duration = time.time() - t0
            if r.status_code == 401 or r.status_code == 403:
                logger.warning("TMDB _request GET %s -> %d (%.3fs) — auth fail", path, r.status_code, duration)
                if not _auth_bad:
                    logger.warning("TMDB API key invalid — disabling TMDB enrichment for this session")
                _auth_bad = True
                return None
            if r.status_code == 404:
                logger.debug("TMDB _request GET %s -> 404 (%.3fs) — not found", path, duration)
                return None
            r.raise_for_status()
            data = r.json()
            logger.debug("TMDB _request GET %s -> %d (%.3fs)", path, r.status_code, duration)
            _cache[cache_key] = (now, data)
            _evict_oldest()
            return data
    except (httpx.TimeoutException, httpx.ConnectError) as e:
        duration = time.time() - t0
        _network_bad = True
        _last_fail_time = time.time()
        if _consecutive_fails == 0:
            logger.warning("TMDB unreachable (network/DNS issue) — disabling for %ds: %s (%.3fs)", _FAIL_COOLDOWN, e, duration)
        _consecutive_fails += 1
        return None
    except Exception as e:
        duration = time.time() - t0
        _consecutive_fails += 1
        _last_fail_time = time.time()
        logger.warning("TMDB _request GET %s error after %.3fs: %s", path, duration, e)
        return None


def _img(path: Optional[str], size: str = "w500") -> Optional[str]:
    """Build full image URL from TMDB poster/backdrop path."""
    if not path:
        return None
    return f"{settings.tmdb_image_base}{size}{path}"


async def get_imdb_details(imdb_id: str) -> Optional[dict]:
    """Fetch TMDB details for an IMDB id (e.g. 'tt0111161').

    Returns a dict with keys: id, imdb_id, title, original_title, overview,
    poster_url, backdrop_url, year, rating, vote_count, genres, runtime,
    cast, director, type ('movie' or 'tv'), tmdb_id — or None on failure.
    """
    if not imdb_id or not imdb_id.startswith("tt"):
        return None
    data = await _request(f"/find/{imdb_id}", params={"external_source": "imdb_id"})
    if not data:
        logger.debug("TMDB get_imdb_details(%s) — not found (no find data)", imdb_id)
        return None
    results = data.get("movie_results") or []
    media_type = "movie"
    item = results[0] if results else None
    if not item:
        results = data.get("tv_results") or []
        item = results[0] if results else None
        media_type = "tv"
    if not item:
        logger.debug("TMDB get_imdb_details(%s) — not found (no movie/tv results)", imdb_id)
        return None

    tmdb_id = item.get("id")
    details_path = f"/movie/{tmdb_id}" if media_type == "movie" else f"/tv/{tmdb_id}"
    details = await _request(details_path, params={"append_to_response": "credits"})
    if not details:
        logger.debug("TMDB get_imdb_details(%s) — tmdb_id=%s details not found", imdb_id, tmdb_id)
        return None

    if media_type == "movie":
        title = details.get("title") or details.get("original_title")
        year = (details.get("release_date") or "")[:4]
        runtime = details.get("runtime", 0)
    else:
        title = details.get("name") or details.get("original_name")
        year = (details.get("first_air_date") or "")[:4]
        runtime = details.get("episode_run_time", [0])[0] if details.get("episode_run_time") else 0

    genres = [g.get("name") for g in details.get("genres", []) if g.get("name")]
    cast = []
    director = ""
    for c in (details.get("credits", {}) or {}).get("cast", [])[:10]:
        cast.append({
            "id": c.get("id"),
            "name": c.get("name"),
            "character": c.get("character"),
            "profile_url": _img(c.get("profile_path"), "w185"),
        })
    for crew in (details.get("credits", {}) or {}).get("crew", []):
        if crew.get("job") == "Director":
            director = crew.get("name", "")
            break

    logger.debug("TMDB get_imdb_details(%s) — found tmdb_id=%s type=%s title=%s", imdb_id, tmdb_id, media_type, title)
    return {
        "tmdb_id": tmdb_id,
        "imdb_id": imdb_id,
        "title": title,
        "year": year,
        "overview": details.get("overview", ""),
        "tagline": details.get("tagline", ""),
        "poster_url": _img(details.get("poster_path"), "w500"),
        "backdrop_url": _img(details.get("backdrop_path"), "w1280"),
        "rating": details.get("vote_average", 0),
        "vote_count": details.get("vote_count", 0),
        "genres": genres,
        "runtime_min": runtime,
        "cast": cast,
        "director": director,
        "type": media_type,
        "status": details.get("status", ""),
        "original_language": details.get("original_language", ""),
    }


async def get_recommendations(imdb_id: str, limit: int = 20) -> List[dict]:
    """Get TMDB recommendations based on an IMDB id."""
    details = await get_imdb_details(imdb_id)
    if not details:
        return []
    tmdb_id = details.get("tmdb_id")
    media_type = details.get("type", "movie")
    if not tmdb_id:
        return []
    rec_path = f"/{media_type}/{tmdb_id}/recommendations"
    data = await _request(rec_path)
    if not data:
        logger.debug("TMDB get_recommendations(imdb_id=%s) — 0 results (no data)", imdb_id)
        return []
    results = []
    for r in (data.get("results") or [])[:limit]:
        if media_type == "movie":
            t = r.get("title") or r.get("original_title")
            y = (r.get("release_date") or "")[:4]
        else:
            t = r.get("name") or r.get("original_name")
            y = (r.get("first_air_date") or "")[:4]
        results.append({
            "tmdb_id": r.get("id"),
            "title": t,
            "year": y,
            "rating": r.get("vote_average", 0),
            "overview": r.get("overview", ""),
            "poster_url": _img(r.get("poster_path"), "w500"),
            "backdrop_url": _img(r.get("backdrop_path"), "w1280"),
            "type": media_type,
        })
    logger.debug("TMDB get_recommendations(imdb_id=%s) — %d results", imdb_id, len(results))
    return results


async def search(query: str, media_type: str = "movie", limit: int = 10) -> List[dict]:
    """Search TMDB for a title. Useful for filling in missing catalog data."""
    if not query or len(query.strip()) < 2:
        return []
    data = await _request(f"/search/{media_type}", params={"query": query, "page": 1})
    if not data:
        logger.debug("TMDB search(query=%r, media_type=%s) — 0 results (no data)", query, media_type)
        return []
    results = []
    for r in (data.get("results") or [])[:limit]:
        if media_type == "movie":
            t = r.get("title") or r.get("original_title")
            y = (r.get("release_date") or "")[:4]
        else:
            t = r.get("name") or r.get("original_name")
            y = (r.get("first_air_date") or "")[:4]
        results.append({
            "tmdb_id": r.get("id"),
            "title": t,
            "year": y,
            "rating": r.get("vote_average", 0),
            "overview": r.get("overview", ""),
            "poster_url": _img(r.get("poster_path"), "w500"),
            "backdrop_url": _img(r.get("backdrop_path"), "w1280"),
            "type": media_type,
        })
    logger.debug("TMDB search(query=%r, media_type=%s) — %d results", query, media_type, len(results))
    return results


async def get_genres(media_type: str = "movie") -> List[dict]:
    """Get the list of TMDB genre names + ids for movies or TV."""
    data = await _request(f"/genre/{media_type}/list")
    if not data:
        logger.debug("TMDB get_genres(%s) — 0 results (no data)", media_type)
        return []
    result = data.get("genres", [])
    logger.debug("TMDB get_genres(%s) — %d genres", media_type, len(result))
    return result


async def discover_by_genre(genre_id: int, media_type: str = "movie", page: int = 1) -> List[dict]:
    """Discover titles by TMDB genre id, sorted by popularity."""
    data = await _request(
        f"/discover/{media_type}",
        params={
            "with_genres": genre_id,
            "sort_by": "popularity.desc",
            "page": page,
            "vote_count.gte": 50,
        }
    )
    if not data:
        logger.debug("TMDB discover_by_genre(genre_id=%d, media_type=%s, page=%d) — 0 results (no data)", genre_id, media_type, page)
        return []
    results = []
    for r in (data.get("results") or []):
        if media_type == "movie":
            t = r.get("title") or r.get("original_title")
            y = (r.get("release_date") or "")[:4]
        else:
            t = r.get("name") or r.get("original_name")
            y = (r.get("first_air_date") or "")[:4]
        results.append({
            "tmdb_id": r.get("id"),
            "title": t,
            "year": y,
            "rating": r.get("vote_average", 0),
            "overview": r.get("overview", ""),
            "poster_url": _img(r.get("poster_path"), "w500"),
            "backdrop_url": _img(r.get("backdrop_path"), "w1280"),
            "type": media_type,
        })
    logger.debug("TMDB discover_by_genre(genre_id=%d, media_type=%s, page=%d) — %d results", genre_id, media_type, page, len(results))
    return results


def reset_auth_badge():
    """Allow retrying after the user updates their TMDB_API_KEY or network recovers."""
    global _auth_bad, _network_bad, _consecutive_fails, _last_fail_time
    logger.debug("TMDB reset_auth_badge() called — clearing fail flags and cache")
    _auth_bad = False
    _network_bad = False
    _consecutive_fails = 0
    _last_fail_time = 0.0
    _cache.clear()
