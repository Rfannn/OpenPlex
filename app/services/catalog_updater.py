import asyncio
import json
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from sqlalchemy.exc import OperationalError

from app.services.scraper import fetch_archive, parse_archive
from app.services.catalog_enricher import enrich_covers_only
from app.models.download_catalog import DownloadCatalog
from app.database import async_session

logger = logging.getLogger(__name__)


async def update_catalog(db: AsyncSession):
    logger.info("Starting catalog update...")
    html = await fetch_archive()
    if not html:
        logger.error("Failed to fetch archive page")
        return False

    entries = await parse_archive(html)
    if not entries:
        logger.error("No entries parsed from archive")
        return False

    count = 0
    errors = 0
    for entry in entries:
        try:
            stmt = select(DownloadCatalog).where(DownloadCatalog.imdb_code == entry["imdb_code"])
            result = await db.execute(stmt)
            existing = result.scalar_one_or_none()

            if existing:
                existing.title = entry["title"]
                existing.year = entry["year"]
                existing.title_type = entry["title_type"]
                existing.imdb_rating = entry["imdb_rating"]
                existing.imdb_votes = entry["imdb_votes"]
                existing.softsub_links = json.dumps(entry["softsub_links"])
                existing.dubbed_links = json.dumps(entry["dubbed_links"])
                existing.nosub_links = json.dumps(entry["nosub_links"])
                existing.has_seasons = entry["has_seasons"]
                existing.season_info = json.dumps(entry["season_info"])
            else:
                cat = DownloadCatalog(
                    imdb_code=entry["imdb_code"],
                    title=entry["title"],
                    year=entry["year"],
                    title_type=entry["title_type"],
                    imdb_rating=entry["imdb_rating"],
                    imdb_votes=entry["imdb_votes"],
                    softsub_links=json.dumps(entry["softsub_links"]),
                    dubbed_links=json.dumps(entry["dubbed_links"]),
                    nosub_links=json.dumps(entry["nosub_links"]),
                    has_seasons=entry["has_seasons"],
                    season_info=json.dumps(entry["season_info"]),
                )
                db.add(cat)
            count += 1
        except Exception as e:
            errors += 1
            logger.warning(f"Error processing catalog entry {entry.get('imdb_code', '?')}: {e}")
            continue

    try:
        await db.commit()
    except Exception as e:
        logger.error(f"Failed to commit catalog update: {e}")
        await db.rollback()
        return False

    logger.info(f"Catalog updated: {count} entries ({errors} errors)")
    return True


async def enrich_catalog_covers(db: AsyncSession, limit: int = 30):
    """Enrich catalog entries with TMDB covers. Call with its own session."""
    enriched = 0
    for attempt in range(3):
        try:
            enriched = await enrich_covers_only(db, limit=limit)
            if enriched:
                logger.info(f"Cover enrichment: {enriched} covers added")
            break
        except OperationalError as ex:
            if "database is locked" in str(ex):
                logger.warning(f"Database locked, retrying ({attempt+1}/3)...")
                await asyncio.sleep(1 * (attempt + 1))
                continue
            logger.warning(f"Cover enrichment failed: {ex}")
            break
        except Exception as ex:
            logger.warning(f"Cover enrichment failed: {ex}")
            break
    return enriched
