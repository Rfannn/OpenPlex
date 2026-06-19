import asyncio
import json
import logging
import os
import time
from pathlib import Path
from typing import Optional, Dict, List, Set
import aiofiles
import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.download_catalog import DownloadCatalog

logger = logging.getLogger(__name__)
COVERS_DIR = Path(__file__).resolve().parent.parent.parent / "static" / "covers"

_SEMAPHORE = asyncio.Semaphore(5)

# Retry-after-cooldown: failed codes map to timestamp of last failure.
# Codes are retried after RETRY_COOLDOWN seconds (1 hour).
RETRY_COOLDOWN = 3600
_FAILED_CODES_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "failed_covers.json"
_FAILED_CODES: Dict[str, float] = {}
if _FAILED_CODES_FILE.exists():
    try:
        raw = json.loads(_FAILED_CODES_FILE.read_text())
        # Migrate old list format to dict format
        if isinstance(raw, list):
            now = time.time()
            _FAILED_CODES = {code: now for code in raw}
        elif isinstance(raw, dict):
            _FAILED_CODES = raw
    except Exception:
        _FAILED_CODES = {}


def _save_failed_codes():
    try:
        _FAILED_CODES_FILE.write_text(json.dumps(_FAILED_CODES))
        logger.debug(f"_save_failed_codes: saved {len(_FAILED_CODES)} entries")
    except Exception as e:
        logger.warning(f"_save_failed_codes: failed to save failed_codes: {e}")


def _is_permanently_failed(imdb_code: str) -> bool:
    """Check if a code is in cooldown. Returns True if it should be skipped."""
    ts = _FAILED_CODES.get(imdb_code)
    if ts is None:
        return False
    # Retry if cooldown has elapsed
    elapsed = time.time() - ts
    if elapsed > RETRY_COOLDOWN:
        logger.debug(f"_is_permanently_failed: {imdb_code} cooldown expired ({elapsed:.0f}s), retrying")
        del _FAILED_CODES[imdb_code]
        _save_failed_codes()
        return False
    logger.debug(f"_is_permanently_failed: {imdb_code} in cooldown ({elapsed:.0f}s / {RETRY_COOLDOWN}s)")
    return True


async def download_cover(imdb_code: str) -> bool:
    """Download cover from TMDB, Fanart.tv, or myf2m.org to local cache. Returns True if file exists locally after attempt."""
    logger.debug(f"download_cover: entry imdb_code={imdb_code}")
    COVERS_DIR.mkdir(parents=True, exist_ok=True)
    local = COVERS_DIR / f"{imdb_code}.jpg"
    if local.exists():
        logger.debug(f"download_cover: cache HIT for {imdb_code}")
        return True
    logger.debug(f"download_cover: cache MISS for {imdb_code}")

    # Try myf2m first (unreliable external APIs in cooldown, but myf2m is live)
    poster_url = await _try_myf2m(imdb_code)

    if not poster_url and not _is_permanently_failed(imdb_code):
        # Try TMDB first
        try:
            from app.services import tmdb
            if tmdb.is_configured():
                logger.debug(f"download_cover: {imdb_code} querying TMDB")
                data = await tmdb._request(f"/find/{imdb_code}", {"external_source": "imdb_id"})
                if data:
                    posters = data.get("movie_results") or data.get("tv_results")
                    if posters and posters[0].get("poster_path"):
                        poster_url = f"https://image.tmdb.org/t/p/w500{posters[0]['poster_path']}"
                        logger.debug(f"download_cover: {imdb_code} got poster_url from TMDB")
        except Exception as e:
            logger.warning(f"download_cover: {imdb_code} TMDB lookup failed: {e}")

        # Try Fanart.tv as backup (high-res)
        if not poster_url:
            try:
                from app.services import fanart
                if fanart.is_configured():
                    logger.debug(f"download_cover: {imdb_code} querying Fanart.tv")
                    fanart_poster = await fanart.get_best_poster(imdb_code)
                    if fanart_poster:
                        poster_url = fanart_poster
                        logger.debug(f"download_cover: {imdb_code} got poster_url from Fanart.tv")
            except Exception as e:
                logger.warning(f"download_cover: {imdb_code} Fanart.tv lookup failed: {e}")

    # Download the image
    if poster_url:
        try:
            async with _SEMAPHORE:
                async with httpx.AsyncClient(timeout=15) as client:
                    resp = await client.get(poster_url)
                    if resp.status_code == 200:
                        async with aiofiles.open(local, "wb") as f:
                            await f.write(resp.content)
                        logger.debug(f"download_cover: {imdb_code} downloaded successfully from {poster_url}")
                        # Remove from failed list if present
                        _FAILED_CODES.pop(imdb_code, None)
                        _save_failed_codes()
                        return True
                    else:
                        logger.warning(f"download_cover: {imdb_code} HTTP {resp.status_code} from {poster_url}")
        except Exception as e:
            logger.warning(f"download_cover: {imdb_code} download failed: {e}")

    # All sources failed — mark with cooldown
    logger.warning(f"download_cover: all sources failed for {imdb_code}, marking cooldown")
    _FAILED_CODES[imdb_code] = time.time()
    _save_failed_codes()
    return False


async def _try_myf2m(imdb_code: str) -> Optional[str]:
    """Try to get a cover URL from myf2m.org. Bypasses the cooldown since myf2m is a live scraper."""
    try:
        from app.services.myf2m_scraper import get_myf2m_cover
        myf2m_url = await get_myf2m_cover(imdb_code)
        if myf2m_url:
            logger.debug(f"download_cover: {imdb_code} got poster_url from myf2m.org")
            return myf2m_url
    except Exception as e:
        logger.warning(f"download_cover: {imdb_code} myf2m lookup failed: {e}")
    return None


async def download_covers_batch(imdb_codes: List[str]) -> Set[str]:
    """Download multiple covers in parallel. Returns set of imdb_codes that succeeded."""
    logger.debug(f"download_covers_batch: starting batch of {len(imdb_codes)} codes")
    if not imdb_codes:
        logger.debug("download_covers_batch: empty batch, returning")
        return set()
    tasks = {code: download_cover(code) for code in imdb_codes}
    results = await asyncio.gather(*tasks.values())
    ok_codes = {code for code, ok in zip(tasks.keys(), results) if ok}
    logger.debug(f"download_covers_batch: finished batch, {len(ok_codes)}/{len(imdb_codes)} succeeded")
    return ok_codes


async def enrich_covers_only(db: AsyncSession, limit: int = 50) -> int:
    """Fast batch: download covers in parallel for entries missing them. limit=0 means no limit."""
    logger.debug(f"enrich_covers_only: entry limit={limit}")
    stmt = select(DownloadCatalog).where(DownloadCatalog.cover_url == "")
    if limit:
        stmt = stmt.limit(limit)
    result = await db.execute(stmt)
    entries = result.scalars().all()
    if not entries:
        logger.debug("enrich_covers_only: no entries missing covers")
        return 0

    codes = [e.imdb_code for e in entries]
    logger.info(f"enrich_covers_only: batch size={len(codes)}")
    ok_codes = await download_covers_batch(codes)
    for e in entries:
        if e.imdb_code in ok_codes:
            e.cover_url = f"/static/covers/{e.imdb_code}.jpg"
    await db.commit()
    if ok_codes:
        logger.info(f"enrich_covers_only: downloaded {len(ok_codes)}/{len(codes)} covers")

    remaining = [e for e in entries if not e.cover_url and e.title]
    if remaining:
        logger.debug(f"enrich_covers_only: {len(remaining)} entries still missing covers (will retry on next cycle)")
    else:
        logger.debug(f"enrich_covers_only: downloaded 0/{len(codes)} covers")
    logger.debug(f"enrich_covers_only: returning {len(ok_codes)}")
    return len(ok_codes)


async def fix_start_year_artifacts(db: AsyncSession) -> int:
    """One-time cleanup: strip ' start_year' suffix from all catalog titles."""
    logger.debug("fix_start_year_artifacts: entry")
    from sqlalchemy import update
    result = await db.execute(
        select(DownloadCatalog).where(DownloadCatalog.title.like("% start_year"))
    )
    entries = result.scalars().all()
    if not entries:
        logger.debug("fix_start_year_artifacts: no artifacts found")
        return 0
    count = 0
    for entry in entries:
        if entry.title and " start_year" in entry.title:
            entry.title = entry.title.replace(" start_year", "").strip()
            count += 1
    await db.commit()
    logger.info(f"fix_start_year_artifacts: fixed {count} titles with start_year artifact")
    logger.debug("fix_start_year_artifacts: returning")
    return count