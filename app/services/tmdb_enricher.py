"""TMDB + OMDb + TVDb + Fanart enrichment for the download catalog.

Fills in backdrop, overview, genres, cast, runtime, director, etc.
on existing catalog rows. Used to power the Netflix-like library UI.
"""
import asyncio
import json
import logging
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.download_catalog import DownloadCatalog
from app.services import tmdb, omdb, tvdb as tvdb_service, fanart

logger = logging.getLogger(__name__)

# Track available data sources at module level for logging
_SOURCE_NAMES = {
    "tmdb": "TMDB",
    "omdb": "OMDb",
    "fanart": "Fanart.tv",
    "tvdb": "TVDb",
}

_SEMAPHORE = asyncio.Semaphore(3)


def _apply_data(entry: DownloadCatalog, data: dict, source_label: str = "unknown") -> bool:
    """Apply a metadata dict to a catalog entry. Returns True if changed."""
    changed = False
    fields_applied = []

    if data.get("year") and not entry.year:
        entry.year = str(data["year"])
        changed = True
        fields_applied.append("year")
    if data.get("overview") and not entry.overview:
        entry.overview = data["overview"][:4000]
        changed = True
        fields_applied.append("overview")
    if data.get("tagline") and not entry.tagline:
        entry.tagline = data["tagline"][:512]
        changed = True
        fields_applied.append("tagline")
    if data.get("backdrop_url") and not entry.backdrop_url:
        entry.backdrop_url = data["backdrop_url"]
        changed = True
        fields_applied.append("backdrop_url")
    if data.get("genres"):
        new_genres = json.dumps(data["genres"])
        if entry.genres_json in (None, "", "[]"):
            entry.genres_json = new_genres
            changed = True
            fields_applied.append("genres")
    if data.get("runtime_min") and not entry.runtime_min:
        entry.runtime_min = int(data["runtime_min"])
        changed = True
        fields_applied.append("runtime_min")
    if data.get("director") and not entry.director:
        entry.director = data["director"][:256]
        changed = True
        fields_applied.append("director")
    if data.get("cast"):
        new_cast = json.dumps(data["cast"])
        if entry.cast_json in (None, "", "[]"):
            entry.cast_json = new_cast
            changed = True
            fields_applied.append("cast")
    if data.get("tmdb_id") and not entry.tmdb_id:
        entry.tmdb_id = int(data["tmdb_id"])
        changed = True
        fields_applied.append("tmdb_id")
    if data.get("imdb_rating") and not entry.imdb_rating:
        entry.imdb_rating = str(data["imdb_rating"])
        changed = True
        fields_applied.append("imdb_rating")
    if data.get("imdb_votes") and not entry.imdb_votes:
        entry.imdb_votes = str(data["imdb_votes"])
        changed = True
        fields_applied.append("imdb_votes")
    # Fanart high-res backdrop (takes priority over TMDB)
    if data.get("fanart_backdrop") and data["fanart_backdrop"].startswith("http"):
        entry.backdrop_url = data["fanart_backdrop"]
        changed = True
        fields_applied.append("backdrop_url(fanart_hires)")

    if fields_applied:
        logger.debug(
            "Applied fields from %s to entry %s (id=%s): %s",
            source_label, entry.title, entry.id, ", ".join(fields_applied),
        )
    else:
        logger.debug(
            "No new fields applied from %s to entry %s (id=%s) — already populated or unavailable",
            source_label, entry.title, entry.id,
        )
    return changed


async def enrich_with_tmdb(db: AsyncSession, entry: DownloadCatalog) -> bool:
    """Enrich a single catalog entry with TMDB data.

    Falls back to OMDb if TMDB is unavailable.
    Supplements TV series with TVDb data.
    Upgrades backdrops with Fanart.tv high-res art.
    """
    if not entry.imdb_code or not entry.imdb_code.startswith("tt"):
        logger.debug(
            "Skipping entry id=%s title=%s: no valid imdb_code (%s)",
            entry.id, entry.title, entry.imdb_code,
        )
        return False
    if entry.overview and entry.cast_json and entry.cast_json != "[]":
        logger.debug(
            "Skipping entry id=%s title=%s imdb=%s: already enriched (overview+cast present)",
            entry.id, entry.title, entry.imdb_code,
        )
        return False

    # Log which sources are configured
    sources_available = []
    if tmdb.is_configured():
        sources_available.append("TMDB")
    if omdb.is_configured():
        sources_available.append("OMDb")
    if tvdb_service.is_configured():
        sources_available.append("TVDb")
    if fanart.is_configured():
        sources_available.append("Fanart.tv")

    logger.debug(
        "Enriching entry id=%s title=%s imdb=%s title_type=%s | sources_available=%s",
        entry.id, entry.title, entry.imdb_code, entry.title_type,
        ", ".join(sources_available) if sources_available else "NONE",
    )

    data = None
    changed = False
    sources_queried = []

    async with _SEMAPHORE:
        # 1. Try TMDB first
        if tmdb.is_configured():
            sources_queried.append("TMDB")
            try:
                logger.debug("Querying TMDB for %s (entry id=%s)", entry.imdb_code, entry.id)
                data = await tmdb.get_imdb_details(entry.imdb_code)
                if data:
                    logger.debug(
                        "TMDB returned data for %s (entry id=%s): title=%s, has_overview=%s, has_cast=%s, has_backdrop=%s",
                        entry.imdb_code, entry.id,
                        data.get("title", "N/A"),
                        bool(data.get("overview")),
                        bool(data.get("cast")),
                        bool(data.get("backdrop_url")),
                    )
                else:
                    logger.debug("TMDB returned no data for %s (entry id=%s)", entry.imdb_code, entry.id)
            except Exception as e:
                logger.warning("TMDB enrich error for %s (entry id=%s): %s", entry.imdb_code, entry.id, e)
        else:
            logger.debug("Skipping TMDB for entry id=%s: TMDB not configured", entry.id)

        # 2. OMDb backup if TMDB failed
        if not data:
            if omdb.is_configured():
                sources_queried.append("OMDb")
                try:
                    logger.debug("Falling back to OMDb for %s (entry id=%s)", entry.imdb_code, entry.id)
                    omdb_data = await omdb.get_by_imdb(entry.imdb_code)
                    if omdb_data:
                        logger.debug(
                            "OMDb returned data for %s (entry id=%s): title=%s, has_overview=%s",
                            entry.imdb_code, entry.id,
                            omdb_data.get("title", "N/A"),
                            bool(omdb_data.get("plot")),
                        )
                        data = {
                            "title": omdb_data.get("title"),
                            "year": omdb_data.get("year"),
                            "overview": omdb_data.get("plot"),
                            "genres": omdb_data.get("genre", []),
                            "director": omdb_data.get("director", ""),
                            "cast": [{"name": a} for a in omdb_data.get("actors", [])],
                            "runtime_min": omdb_data.get("runtime_min", 0),
                            "imdb_rating": omdb_data.get("imdb_rating", ""),
                            "imdb_votes": omdb_data.get("imdb_votes", ""),
                            "tagline": "",
                            "backdrop_url": "",
                            "tmdb_id": None,
                        }
                    else:
                        logger.debug("OMDb returned no data for %s (entry id=%s)", entry.imdb_code, entry.id)
                except Exception as e:
                    logger.warning("OMDb enrich error for %s (entry id=%s): %s", entry.imdb_code, entry.id, e)
            else:
                logger.debug("Skipping OMDb fallback for entry id=%s: OMDb not configured", entry.id)

    if not data:
        logger.debug(
            "No data from any source for entry id=%s title=%s imdb=%s | queried=%s",
            entry.id, entry.title, entry.imdb_code,
            ", ".join(sources_queried) if sources_queried else "none",
        )
        return False

    # Clean up title
    if data.get("title") and entry.title:
        if " start_year" in entry.title:
            entry.title = entry.title.replace(" start_year", "").strip()
            changed = True
        elif len(entry.title) > 80 or not entry.title:
            entry.title = data["title"]
            changed = True

    # Source label: use the first source that gave us data
    source_label = sources_queried[0] if sources_queried else "unknown"
    changed = _apply_data(entry, data, source_label=source_label) or changed

    # 3. Fanart.tv high-res backdrop (upgrade)
    if fanart.is_configured():
        sources_queried.append("Fanart.tv")
        async with _SEMAPHORE:
            try:
                logger.debug("Querying Fanart.tv for backdrop for %s (entry id=%s)", entry.imdb_code, entry.id)
                backdrop = await fanart.get_best_backdrop(entry.imdb_code)
                if backdrop and backdrop.startswith("http"):
                    entry.backdrop_url = backdrop
                    changed = True
                    logger.debug(
                        "Fanart.tv set backdrop for entry id=%s title=%s: %s",
                        entry.id, entry.title, backdrop[:80],
                    )
                else:
                    logger.debug("Fanart.tv returned no valid backdrop for %s (entry id=%s)", entry.imdb_code, entry.id)
            except Exception as e:
                logger.warning("Fanart.tv enrich error for %s (entry id=%s): %s", entry.imdb_code, entry.id, e)
    else:
        logger.debug("Skipping Fanart.tv for entry id=%s: Fanart.tv not configured", entry.id)

    # 4. TVDb supplement for series
    if entry.title_type == "series" and tvdb_service.is_configured():
        sources_queried.append("TVDb")
        needs_supplement = (not data.get("genres") or not entry.cast_json or entry.cast_json == "[]")
        logger.debug(
            "TVDb supplement check for entry id=%s title=%s: needs_supplement=%s (has_genres=%s, has_cast=%s)",
            entry.id, entry.title,
            needs_supplement,
            bool(data.get("genres")),
            bool(entry.cast_json and entry.cast_json != "[]"),
        )
        if needs_supplement:
            async with _SEMAPHORE:
                try:
                    logger.debug("Querying TVDb for series '%s' (entry id=%s)", entry.title, entry.id)
                    tvdb_results = await tvdb_service.search(entry.title)
                    if tvdb_results:
                        tv_info = tvdb_results[0]
                        tvdb_id = tv_info.get("id")
                        logger.debug("TVDb found series id=%s for '%s' (entry id=%s)", tvdb_id, entry.title, entry.id)
                        if tvdb_id:
                            artwork = await tvdb_service.get_series_artwork(tvdb_id)
                            if artwork:
                                logger.debug("TVDb returned %d artwork items for series id=%s", len(artwork), tvdb_id)
                                for a in artwork[:3]:
                                    if "backdrop" in (a.get("type", "")).lower() and a.get("url") and not entry.backdrop_url:
                                        entry.backdrop_url = a["url"]
                                        changed = True
                                        logger.debug(
                                            "TVDb set backdrop for entry id=%s title=%s: %s",
                                            entry.id, entry.title, a["url"][:80],
                                        )
                            else:
                                logger.debug("TVDb returned no artwork for series id=%s (entry id=%s)", tvdb_id, entry.id)
                    else:
                        logger.debug("TVDb search returned no results for '%s' (entry id=%s)", entry.title, entry.id)
                except Exception as e:
                    logger.warning("TVDb enrich error for entry id=%s title=%s: %s", entry.id, entry.title, e)
    elif entry.title_type == "series":
        logger.debug("Skipping TVDb for entry id=%s title=%s: TVDb not configured", entry.id, entry.title)

    # Summary
    fields = []
    if entry.overview: fields.append("overview")
    if entry.genres_json and entry.genres_json not in ("", "[]"): fields.append("genres")
    if entry.cast_json and entry.cast_json not in ("", "[]"): fields.append("cast")
    if entry.backdrop_url: fields.append("backdrop")
    if entry.year: fields.append("year")
    if entry.director: fields.append("director")
    if entry.runtime_min: fields.append("runtime_min")
    if entry.tmdb_id: fields.append("tmdb_id")
    if entry.imdb_rating: fields.append("imdb_rating")

    logger.debug(
        "Enrich complete for entry id=%s title=%s imdb=%s | sources_queried=%s | changed=%s | present_fields=%s",
        entry.id, entry.title, entry.imdb_code,
        ", ".join(sources_queried) if sources_queried else "none",
        changed,
        ", ".join(fields) if fields else "none",
    )

    return changed


async def enrich_batch(db: AsyncSession, limit: int = 50) -> int:
    """Enrich up to `limit` catalog rows that are missing overview/genres.

    Returns the number of rows updated.
    """
    if not tmdb.is_configured() and not omdb.is_configured() and not tvdb_service.is_configured():
        logger.info("No metadata sources configured (TMDB/OMDb/TVDb all disabled) — skipping batch enrich")
        return 0

    stmt = (
        select(DownloadCatalog)
        .where(DownloadCatalog.overview == "")
        .limit(limit)
    )
    result = await db.execute(stmt)
    entries = result.scalars().all()
    batch_size = len(entries)
    logger.info("Batch enrich started: limit=%d, rows_found=%d", limit, batch_size)

    if batch_size == 0:
        logger.info("Batch enrich complete: no rows pending enrichment")
        return 0

    updated = 0
    skipped = 0
    for idx, entry in enumerate(entries, start=1):
        try:
            changed = await enrich_with_tmdb(db, entry)
            if changed:
                updated += 1
            else:
                skipped += 1
        except Exception as e:
            logger.warning(
                "Enrich loop error for entry id=%s title=%s imdb=%s (idx=%d/%d): %s",
                entry.id, entry.title, entry.imdb_code, idx, batch_size, e,
            )
            skipped += 1

        if idx % 10 == 0 or idx == batch_size:
            logger.debug(
                "Batch progress: %d/%d entries processed (updated=%d, skipped=%d)",
                idx, batch_size, updated, skipped,
            )

    if updated:
        await db.commit()
        logger.info(
            "Batch enrich complete: %d/%d rows updated, %d skipped, committed",
            updated, batch_size, skipped,
        )
    else:
        logger.info(
            "Batch enrich complete: 0/%d rows updated (all %d skipped, nothing to commit)",
            batch_size, skipped,
        )

    return updated
