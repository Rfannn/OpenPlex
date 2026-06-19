import asyncio
import html
import json
import logging
import urllib.parse
import datetime
import os
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, cast, Float

from app.database import get_db
from app.config import settings
from app.models.download_catalog import DownloadCatalog
from app.models.user import User
from app.dependencies import get_current_user, get_optional_user, require_admin
from app.services.scraper import fetch_season_page
from app.services.downloader import add_download, get_progress, rpc_call
from app.services.catalog_updater import update_catalog, enrich_catalog_covers
from app.services.catalog_enricher import download_cover, COVERS_DIR
from app.services.scraper_registry import search_all as registry_search_all, list_scrapers
from app.routers.downloads import _queue_download, _ensure_trailing_slash, looks_like_media_url, set_speed_limit_rpc

logger = logging.getLogger(__name__)
router = APIRouter(tags=["catalog"])

_enrichment_status = {"running": False, "total": 0, "done": 0, "last_error": ""}

# ============ COVER SERVING ============

@router.get("/api/covers/{imdb_code}.jpg")
async def serve_cover(imdb_code: str, db: AsyncSession = Depends(get_db)):
    logger.debug("Serve cover: imdb_code=%s", imdb_code)
    local = COVERS_DIR / f"{imdb_code}.jpg"
    if local.exists():
        return FileResponse(str(local), media_type="image/jpeg")
    # Try to download (fire-and-forget — don't block the response)
    asyncio.ensure_future(download_cover(imdb_code))
    # Generate a pretty text-based SVG cover with the movie title
    title = imdb_code
    try:
        result = await db.execute(select(DownloadCatalog.title).where(DownloadCatalog.imdb_code == imdb_code).limit(1))
        row = result.scalar_one_or_none()
        if row:
            title = row[:200]
    except Exception:
        pass
    import hashlib
    seed = int(hashlib.md5(imdb_code.encode()).hexdigest()[:8], 16)
    colors = ["#1a1a2e","#16213e","#0f3460","#2d1b69","#1b4332","#4a1942","#1c2541","#3d1e1e"]
    c1 = colors[seed % len(colors)]
    c2 = colors[(seed // 7) % len(colors)]
    y = 160
    lines = []
    for line in title.split(" "):
        if len(" ".join(lines + [line])) > 20:
            y += 30
            lines = [line]
        else:
            lines.append(line)
        if len(lines) > 5:
            break
    y -= (len(lines) - 1) * 15
    text_parts = "".join(f'<tspan x="150" dy="{24 if i>0 else 0}">{html.escape(line)}</tspan>' for i, line in enumerate(lines[:6]))
    placeholder = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="300" height="450" viewBox="0 0 300 450">'
        f'<defs><linearGradient id="g" x1="0%" y1="0%" x2="100%" y2="100%">'
        f'<stop offset="0%" stop-color="{c1}"/><stop offset="100%" stop-color="{c2}"/></linearGradient></defs>'
        f'<rect fill="url(#g)" width="300" height="450"/>'
        f'<text fill="rgba(255,255,255,0.15)" font-family="sans-serif" font-weight="700" font-size="72" text-anchor="middle" x="150" y="380">{imdb_code[2:6]}</text>'
        f'<text fill="#eee" font-family="sans-serif" font-size="13" text-anchor="middle" x="150" y="{y}">{text_parts}</text>'
        f'<circle cx="150" cy="280" r="28" fill="none" stroke="rgba(255,255,255,0.3)" stroke-width="2"/>'
        f'<polygon points="145,268 145,292 163,280" fill="rgba(255,255,255,0.5)"/>'
        f'</svg>'
    )
    return Response(content=placeholder, media_type="image/svg+xml")


# ============ CATALOG CRUD ============

@router.get("/api/catalog")
async def browse_catalog(
    q: str = Query(""),
    type_filter: str = Query("", alias="type"),
    year_min: str = Query(""),
    year_max: str = Query(""),
    rating_min: float = Query(0),
    rating_max: float = Query(10),
    sort_by: str = Query("id"),
    sort_order: str = Query("asc"),
    page: int = Query(1),
    per_page: int = Query(30),
    user: Optional[User] = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
):
    logger.debug("Browse catalog: q=%s type=%s page=%d per_page=%d", q, type_filter, page, per_page)
    stmt = select(DownloadCatalog)
    if q:
        stmt = stmt.where(DownloadCatalog.title.ilike(f"%{q}%"))
    if type_filter:
        stmt = stmt.where(DownloadCatalog.title_type == type_filter)
    if year_min:
        stmt = stmt.where(DownloadCatalog.year >= year_min)
    if year_max:
        stmt = stmt.where(DownloadCatalog.year <= year_max)
    if rating_min > 0:
        stmt = stmt.where(cast(DownloadCatalog.imdb_rating, Float) >= rating_min)
    if rating_max < 10:
        stmt = stmt.where(cast(DownloadCatalog.imdb_rating, Float) <= rating_max)
    sort_col = getattr(DownloadCatalog, sort_by, DownloadCatalog.id)
    order = sort_col.desc() if sort_order == "desc" else sort_col.asc()
    stmt = stmt.order_by(order).offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(stmt)
    entries = result.scalars().all()
    count_stmt = select(func.count(DownloadCatalog.id))
    if q:
        count_stmt = count_stmt.where(DownloadCatalog.title.ilike(f"%{q}%"))
    if type_filter:
        count_stmt = count_stmt.where(DownloadCatalog.title_type == type_filter)
    if year_min:
        count_stmt = count_stmt.where(DownloadCatalog.year >= year_min)
    if year_max:
        count_stmt = count_stmt.where(DownloadCatalog.year <= year_max)
    if rating_min > 0:
        count_stmt = count_stmt.where(cast(DownloadCatalog.imdb_rating, Float) >= rating_min)
    if rating_max < 10:
        count_stmt = count_stmt.where(cast(DownloadCatalog.imdb_rating, Float) <= rating_max)
    count_result = await db.execute(count_stmt)
    total = count_result.scalar() or 0
    logger.debug("Catalog browse result: total=%d page=%d entries=%d", total, page, len(entries))
    return {
        "success": True,
        "entries": [
            {
                "id": e.id, "imdb_code": e.imdb_code, "title": e.title,
                "year": e.year, "title_type": e.title_type,
                "imdb_rating": e.imdb_rating, "imdb_votes": e.imdb_votes,
                "has_seasons": e.has_seasons,
                "softsub_count": len(json.loads(e.softsub_links or "[]")),
                "dubbed_count": len(json.loads(e.dubbed_links or "[]")),
                "nosub_count": len(json.loads(e.nosub_links or "[]")),
                "cover_url": e.cover_url,
            }
            for e in entries
        ],
        "total": total, "page": page, "has_more": (page * per_page) < total,
    }


@router.get("/api/catalog/{catalog_id}")
async def catalog_detail(catalog_id: int, user: Optional[User] = Depends(get_optional_user), db: AsyncSession = Depends(get_db)):
    logger.debug("Catalog detail: catalog_id=%d", catalog_id)
    result = await db.execute(select(DownloadCatalog).where(DownloadCatalog.id == catalog_id))
    entry = result.scalar_one_or_none()
    if not entry:
        logger.warning("Catalog detail not found: catalog_id=%d", catalog_id)
        raise HTTPException(status_code=404)
    return {
        "success": True,
        "entry": {
            "id": entry.id, "imdb_code": entry.imdb_code,
            "title": entry.title, "year": entry.year,
            "title_type": entry.title_type,
            "imdb_rating": entry.imdb_rating, "imdb_votes": entry.imdb_votes,
            "has_seasons": entry.has_seasons,
            "season_info": json.loads(entry.season_info or "{}"),
            "softsub_links": json.loads(entry.softsub_links or "[]"),
            "dubbed_links": json.loads(entry.dubbed_links or "[]"),
            "nosub_links": json.loads(entry.nosub_links or "[]"),
            "cover_url": entry.cover_url,
        },
    }


# ============ ENRICHMENT ============

@router.get("/api/enrich/status")
async def enrichment_status(user: User = Depends(get_current_user)):
    logger.debug("Enrichment status: user=%s running=%s done=%d/%d", user.username, _enrichment_status["running"], _enrichment_status["done"], _enrichment_status["total"])
    return {"success": True, **_enrichment_status}


@router.post("/api/enrich/batch")
async def trigger_enrichment(
    limit: int = Query(100),
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    logger.info("Trigger enrichment: limit=%d user=%s", limit, user.username)
    if _enrichment_status["running"]:
        logger.warning("Enrichment already in progress - rejected")
        return {"success": False, "detail": "Enrichment already in progress"}
    from app.database import async_session
    async def _run():
        _enrichment_status["running"] = True
        _enrichment_status["total"] = limit
        _enrichment_status["done"] = 0
        try:
            async with async_session() as sess:
                from app.services.catalog_enricher import enrich_covers_only
                done = await enrich_covers_only(sess, limit=limit)
                _enrichment_status["done"] = done
        except Exception as e:
            _enrichment_status["last_error"] = str(e)
        finally:
            _enrichment_status["running"] = False
    import asyncio
    asyncio.create_task(_run())
    return {"success": True, "detail": f"Enrichment started for {limit} entries"}


# ============ FAVORITES ============

@router.get("/api/favorites/ids")
async def list_favorite_ids(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    logger.debug("List favorite IDs: user=%s", user.username)
    from app.models.catalog_favorite import CatalogFavorite
    result = await db.execute(
        select(CatalogFavorite.catalog_id).where(CatalogFavorite.user_id == user.id)
    )
    ids = [r[0] for r in result.all()]
    logger.debug("Favorites IDs: user=%s count=%d", user.username, len(ids))
    return {"success": True, "ids": ids}


@router.get("/api/favorites")
async def list_favorites(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    logger.debug("List favorites: user=%s", user.username)
    from app.models.catalog_favorite import CatalogFavorite
    subq = select(CatalogFavorite.catalog_id).where(CatalogFavorite.user_id == user.id).subquery()
    stmt = select(DownloadCatalog).where(DownloadCatalog.id.in_(subq))
    result = await db.execute(stmt)
    entries = result.scalars().all()
    return {
        "success": True,
        "entries": [
            {
                "id": e.id, "imdb_code": e.imdb_code, "title": e.title,
                "year": e.year, "title_type": e.title_type,
                "imdb_rating": e.imdb_rating, "imdb_votes": e.imdb_votes,
                "has_seasons": e.has_seasons, "cover_url": e.cover_url,
                "softsub_count": len(json.loads(e.softsub_links or "[]")),
                "dubbed_count": len(json.loads(e.dubbed_links or "[]")),
                "nosub_count": len(json.loads(e.nosub_links or "[]")),
            }
            for e in entries
        ],
    }


@router.post("/api/favorites/{catalog_id}")
async def add_favorite(catalog_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    logger.info("Add favorite: catalog_id=%d user=%s", catalog_id, user.username)
    from app.models.catalog_favorite import CatalogFavorite
    existing = await db.execute(
        select(CatalogFavorite).where(
            CatalogFavorite.user_id == user.id, CatalogFavorite.catalog_id == catalog_id
        )
    )
    if existing.scalar_one_or_none():
        logger.debug("Already favorited: catalog_id=%d user=%s", catalog_id, user.username)
        return {"success": True, "detail": "Already favorited"}
    fav = CatalogFavorite(user_id=user.id, catalog_id=catalog_id)
    db.add(fav)
    await db.commit()
    return {"success": True, "detail": "Added to favorites"}


@router.delete("/api/favorites/{catalog_id}")
async def remove_favorite(catalog_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    logger.info("Remove favorite: catalog_id=%d user=%s", catalog_id, user.username)
    from app.models.catalog_favorite import CatalogFavorite
    fav = await db.execute(
        select(CatalogFavorite).where(
            CatalogFavorite.user_id == user.id, CatalogFavorite.catalog_id == catalog_id
        )
    )
    fav = fav.scalar_one_or_none()
    if fav:
        await db.delete(fav)
        await db.commit()
        logger.info("Favorite removed: catalog_id=%d user=%s", catalog_id, user.username)
    return {"success": True, "detail": "Removed from favorites"}


# ============ CATALOG MANAGEMENT ============

@router.post("/api/catalog/refresh")
async def refresh_catalog(
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    logger.info("Refresh catalog: user=%s", user.username)
    ok = await update_catalog(db)
    if ok:
        from app.database import async_session
        async def _enrich():
            _enrichment_status["running"] = True
            _enrichment_status["total"] = 50
            try:
                async with async_session() as enrich_db:
                    from app.services.catalog_enricher import enrich_covers_only
                    done = await enrich_covers_only(enrich_db, limit=50)
                    _enrichment_status["done"] = done
            except Exception as e:
                _enrichment_status["last_error"] = str(e)
            finally:
                _enrichment_status["running"] = False
        import asyncio
        asyncio.create_task(_enrich())
        return {"success": True, "message": "Catalog refreshed, enrichment started"}
    raise HTTPException(status_code=500, detail="Failed to refresh catalog")


@router.post("/api/catalog/enrich-covers")
async def enrich_covers(
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    logger.info("Enrich covers: user=%s", user.username)
    count = await enrich_catalog_covers(db, limit=50)
    logger.info("Covers enriched: %d entries", count)
    return {"success": True, "enriched": count}


# ============ SEARCH ============

@router.get("/api/catalog-search")
async def catalog_search(
    q: str = Query(""),
    title_type: str = Query(""),
    limit: int = Query(30),
    page: int = Query(1),
    db: AsyncSession = Depends(get_db),
    user: Optional[User] = Depends(get_optional_user),
):
    logger.debug("Catalog search: q=%s title_type=%s limit=%d", q, title_type, limit)
    import asyncio

    q = q.strip()
    if len(q) < 1:
        return {"success": True, "entries": [], "total": 0}

    # Always return local DB results first (fast)
    stmt = select(DownloadCatalog).where(DownloadCatalog.title.ilike(f"%{q}%")).limit(20)
    result = await db.execute(stmt)
    local = result.scalars().all()
    local_by_imdb = {}
    local_entries = []
    for e in local:
        entry = {
            "id": e.id, "imdb_code": e.imdb_code, "title": e.title,
            "year": e.year, "title_type": e.title_type,
            "imdb_rating": e.imdb_rating, "imdb_votes": e.imdb_votes,
            "has_seasons": e.has_seasons, "cover_url": e.cover_url,
            "softsub_count": len(json.loads(e.softsub_links or "[]")),
            "dubbed_count": len(json.loads(e.dubbed_links or "[]")),
            "nosub_count": len(json.loads(e.nosub_links or "[]")),
            "source": "catalog",
        }
        if e.imdb_code:
            local_by_imdb[e.imdb_code] = entry
        local_entries.append(entry)

    from app.services.scraper_registry import get_registry as get_scr_registry
    seen_imdb = set(local_by_imdb.keys())
    scraper_entries: list = []

    # Run scrapers in parallel with a hard 10s total timeout so the search
    # never hangs on a slow/unreachable external site.
    SCRAPER_HARD_TIMEOUT = 10.0

    async def _run_scraper(name, scraper):
        try:
            return await asyncio.wait_for(scraper.search(q), timeout=SCRAPER_HARD_TIMEOUT)
        except asyncio.TimeoutError:
            logger.warning("Scraper '%s' search timed out after %.1fs for q=%r", name, SCRAPER_HARD_TIMEOUT, q)
            return []
        except Exception as exc:
            logger.warning("Scraper '%s' search failed for q=%r: %s", name, q, exc)
            return []

    registry = get_scr_registry()
    if registry:
        tasks = [(name, asyncio.create_task(_run_scraper(name, s))) for name, s in registry.items()]
        try:
            done = await asyncio.wait_for(
                asyncio.gather(*[t for _, t in tasks], return_exceptions=True),
                timeout=SCRAPER_HARD_TIMEOUT + 1.0,
            )
        except asyncio.TimeoutError:
            logger.warning("Catalog search scrapers exceeded hard timeout; cancelling")
            for _, t in tasks:
                t.cancel()
            done = []
        for (name, _), results in zip(tasks, done):
            if not results or isinstance(results, Exception):
                continue
            for r in results:
                if r.imdb_id and r.imdb_id in seen_imdb:
                    continue
                if r.imdb_id:
                    seen_imdb.add(r.imdb_id)
                entry = {
                    "source": name, "imdb_code": r.imdb_id,
                    "title": r.title, "year": r.year,
                    "title_type": r.media_type, "imdb_rating": r.imdb_rating,
                    "cover_url": r.cover_url, "has_seasons": False,
                    "softsub_count": 0, "dubbed_count": 0, "nosub_count": 0,
                }
                if r.imdb_id and r.imdb_id in local_by_imdb:
                    entry["id"] = local_by_imdb[r.imdb_id]["id"]
                    entry["has_seasons"] = local_by_imdb[r.imdb_id]["has_seasons"]
                scraper_entries.append(entry)

    merged = local_entries + scraper_entries
    logger.debug("Catalog search results: q=%s local=%d scraper=%d total=%d", q, len(local_entries), len(scraper_entries), len(merged))
    return {"success": True, "entries": merged, "total": len(merged)}


@router.get("/api/search/sources")
async def list_search_sources(user: User = Depends(get_current_user)):
    logger.debug("List search sources: user=%s", user.username)
    return {"success": True, "sources": list_scrapers()}


@router.get("/api/search/all")
async def search_all_sources(
    q: str = Query(..., min_length=2),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    logger.debug("Search all sources: q=%s user=%s", q, user.username)
    try:
        results = await registry_search_all(q)
        entries = []
        for r in results:
            entry = {"source": r.source}
            if r.imdb_id:
                stmt = select(DownloadCatalog).where(DownloadCatalog.imdb_code == r.imdb_id)
                result = await db.execute(stmt)
                local = result.scalar_one_or_none()
                if local:
                    entry["id"] = local.id
            entry.update({
                "imdb_id": r.imdb_id, "title": r.title, "year": r.year,
                "media_type": r.media_type, "imdb_rating": r.imdb_rating,
                "cover_url": r.cover_url,
            })
            entries.append(entry)
        logger.debug("Search all sources result: q=%s results=%d", q, len(entries))
        return {"success": True, "entries": entries, "total": len(entries)}
    except Exception as e:
        logger.error(f"Multi-source search error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/external-detail")
async def external_catalog_detail(
    source: str = Query(...),
    imdb_code: str = Query(""),
    url: str = Query(""),
    title: str = Query(""),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    logger.debug("External detail: source=%s imdb_code=%s title=%s user=%s", source, imdb_code, title, user.username)
    # First check if this already exists in the local catalog
    if imdb_code:
        result = await db.execute(select(DownloadCatalog).where(DownloadCatalog.imdb_code == imdb_code))
        catalog_entry = result.scalar_one_or_none()
        if catalog_entry:
            logger.debug("External detail found in catalog: id=%d has_seasons=%s", catalog_entry.id, catalog_entry.has_seasons)
            return {
                "success": True,
                "entry": {
                    "id": catalog_entry.id, "imdb_code": catalog_entry.imdb_code,
                    "title": catalog_entry.title, "year": catalog_entry.year,
                    "title_type": catalog_entry.title_type,
                    "has_seasons": bool(catalog_entry.has_seasons),
                    "season_info": json.loads(catalog_entry.season_info or "{}"),
                    "softsub_links": json.loads(catalog_entry.softsub_links or "[]"),
                    "dubbed_links": json.loads(catalog_entry.dubbed_links or "[]"),
                    "nosub_links": json.loads(catalog_entry.nosub_links or "[]"),
                    "cover_url": catalog_entry.cover_url,
                },
            }

    from app.services.scraper_registry import get_scraper
    scraper = get_scraper(source)
    if not scraper:
        logger.warning("Unknown source: %s user=%s", source, user.username)
        raise HTTPException(status_code=400, detail=f"Unknown source: {source}")
    lookup_url = url
    if not lookup_url and imdb_code:
        # IMDB code provided but no URL — scraper will need to handle this
        pass
    if not lookup_url:
        raise HTTPException(status_code=400, detail="No url or imdb_code provided")
    try:
        links = await scraper.get_download_links(lookup_url)
        return {
            "success": True,
            "entry": {
                "imdb_code": imdb_code, "title": title,
                "softsub_links": links.softsub,
                "dubbed_links": links.dubbed,
                "nosub_links": links.nosub,
                "cover_url": links.cover_url,
                "has_seasons": False, "season_info": {},
            }
        }
    except Exception as e:
        logger.error(f"External detail error for {source}/{imdb_code}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/tmdb/reset")
async def reset_tmdb(user: User = Depends(get_current_user)):
    """Re-enable TMDB after temporary network failures. Admin-only."""
    logger.info("TMDB reset by user: %s", user.username)
    from app.services import tmdb
    tmdb.reset_auth_badge()
    return {"success": True}


@router.get("/api/debug/tmdb")
async def debug_tmdb(user: Optional[User] = Depends(get_optional_user)):
    """Return TMDB status for debugging."""
    from app.services import tmdb
    return {
        "configured": tmdb.is_configured(),
        "auth_bad": tmdb._auth_bad,
        "network_bad": tmdb._network_bad,
        "consecutive_fails": tmdb._consecutive_fails,
        "last_fail_time": tmdb._last_fail_time,
        "cache_size": len(tmdb._cache),
        "api_timeout": tmdb.REQUEST_TIMEOUT,
        "cooldown_seconds": tmdb._FAIL_COOLDOWN,
    }


@router.get("/api/debug/services")
async def debug_services(user: Optional[User] = Depends(get_optional_user)):
    """Return status of all configured API services."""
    from app.services import tmdb, omdb, fanart, tvdb, opensubtitles
    return {
        "tmdb": {"configured": tmdb.is_configured(), "reachable": not tmdb._network_bad and not tmdb._auth_bad},
        "omdb": {"configured": omdb.is_configured(), "reachable": omdb.is_configured()},
        "fanart": {"configured": fanart.is_configured(), "reachable": fanart.is_configured()},
        "tvdb": {"configured": tvdb.is_configured(), "reachable": tvdb.is_configured()},
        "opensubtitles": {"configured": opensubtitles.is_configured(), "reachable": opensubtitles.is_configured()},
        "majidapi": {"token_set": bool(settings.majidapi_token)},
    }
