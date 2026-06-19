"""Library API — Netflix-style browsing, continue-watching, watchlist, TMDB-driven rows."""

import os
import json
import logging
import random
from pathlib import Path
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, desc, cast, Float, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session, get_db
from app.config import settings
from app.models.user import User
from app.models.download_catalog import DownloadCatalog
from app.models.watch_history import WatchHistory
from app.models.catalog_favorite import CatalogFavorite
from app.dependencies import get_optional_user, get_current_user
from app.services import tmdb
from app.services.cache import response_cache
from app.services.catalog_serializer import serialize_catalog_entry

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/library", tags=["library"])

MEDIA_EXTENSIONS = {
    "Movies": {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm", ".m4v"},
    "Music": {".mp3", ".flac", ".wav", ".aac", ".ogg", ".wma", ".m4a", ".opus"},
    "Images": {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".svg"},
}


def classify_file(name: str) -> Optional[str]:
    ext = Path(name).suffix.lower()
    for section, exts in MEDIA_EXTENSIONS.items():
        if ext in exts:
            return section
    return None


# Use shared serializer from catalog_serializer module
_serialize_catalog_entry = serialize_catalog_entry


@router.get("/rows")
async def library_rows(
    user: Optional[User] = Depends(get_optional_user),
):
    """Return the rows needed for the Netflix-like home page.

    Includes hero (random highly-rated), continue-watching (if logged in),
    several genre rows from the local catalog, and TMDB recommendations
    if a TMDB key is configured.
    """
    logger.debug("Library rows: user=%s", user.username if user else "anonymous")
    cache_key = "library:rows"
    cached = response_cache.get(cache_key)
    if cached:
        return cached

    rows: List[Dict[str, Any]] = []

    try:
        async with async_session() as db:
            # ── Hero: pick the highest-rated entry that has a backdrop or poster ──
            hero_stmt = (
                select(DownloadCatalog)
                .where(cast(DownloadCatalog.imdb_rating, Float) >= 7.0)
                .order_by(desc(cast(DownloadCatalog.imdb_rating, Float)))
                .limit(20)
            )
            hero_rows = (await db.execute(hero_stmt)).scalars().all()
            hero_pick = None
            if hero_rows:
                # Prefer ones with backdrop, then with overview
                with_backdrop = [e for e in hero_rows if e.backdrop_url]
                with_overview = [e for e in hero_rows if e.overview]
                if with_backdrop:
                    hero_pick = with_backdrop[0]
                elif with_overview:
                    hero_pick = with_overview[0]
                else:
                    hero_pick = hero_rows[0]

            if hero_pick:
                rows.append({
                    "type": "hero",
                    "entry": _serialize_catalog_entry(hero_pick),
                })

            # ── Continue watching (only if logged in) ──
            if user:
                cw_stmt = (
                    select(WatchHistory)
                    .where(WatchHistory.user_id == user.id)
                    .order_by(desc(WatchHistory.last_watched))
                    .limit(20)
                )
                cw_rows = (await db.execute(cw_stmt)).scalars().all()
                cw_items = []
                for h in cw_rows:
                    p = Path(h.media_path)
                    if not p.exists():
                        continue
                    if h.duration_sec and (h.position_sec / h.duration_sec) > 0.9:
                        continue
                    # Try to match to a catalog entry by file path
                    cat_id = 0
                    try:
                        match_stmt = select(DownloadCatalog).where(
                            DownloadCatalog.title.ilike(f"%{p.stem[:30]}%")
                        ).limit(1)
                        match = (await db.execute(match_stmt)).scalar_one_or_none()
                        if match:
                            cat_id = match.id
                    except Exception:
                        pass
                    duration = h.duration_sec or 0
                    progress_pct = round((h.position_sec / duration * 100), 1) if duration > 0 else 0
                    cw_items.append({
                        "name": p.name,
                        "path": str(p),
                        "position": h.position_sec,
                        "duration": duration,
                        "progress_pct": progress_pct,
                        "catalog_id": cat_id,
                        "updated_at": h.last_watched.isoformat() if h.last_watched else None,
                    })
                if cw_items:
                    rows.append({"type": "continue", "title": "Continue Watching", "items": cw_items})

            # ── Top rated (overall) ──
            top_stmt = (
                select(DownloadCatalog)
                .where(cast(DownloadCatalog.imdb_rating, Float) >= 6.5)
                .order_by(desc(cast(DownloadCatalog.imdb_rating, Float)))
                .limit(20)
            )
            top_rows = (await db.execute(top_stmt)).scalars().all()
            if top_rows:
                rows.append({
                    "type": "row",
                    "title": "Top Rated",
                    "items": [_serialize_catalog_entry(c) for c in top_rows],
                })

            # ── Genre rows from the catalog ──
            all_stmt = select(DownloadCatalog).where(
                DownloadCatalog.genres_json != "[]",
                DownloadCatalog.genres_json != "",
            ).limit(500)
            all_rows = (await db.execute(all_stmt)).scalars().all()
            by_genre: Dict[str, List[Dict[str, Any]]] = {}
            for c in all_rows:
                try:
                    gs = json.loads(c.genres_json or "[]")
                except Exception:
                    gs = []
                for g in gs:
                    by_genre.setdefault(g, [])
                    if len(by_genre[g]) < 20:
                        by_genre[g].append(_serialize_catalog_entry(c))
            # Sort genres by count, take top 6
            sorted_genres = sorted(by_genre.items(), key=lambda kv: -len(kv[1]))
            for genre, items in sorted_genres[:6]:
                if len(items) >= 3:
                    rows.append({
                        "type": "row",
                        "title": genre,
                        "items": items,
                    })

            # ── Recently added ──
            recent_stmt = (
                select(DownloadCatalog)
                .order_by(desc(DownloadCatalog.last_updated))
                .limit(20)
            )
            recent_rows = (await db.execute(recent_stmt)).scalars().all()
            if recent_rows:
                rows.append({
                    "type": "row",
                    "title": "Recently Added",
                    "items": [_serialize_catalog_entry(c) for c in recent_rows],
                })

            # ── New This Week ──
            nw_stmt = (
                select(DownloadCatalog)
                .where(DownloadCatalog.last_updated >= func.datetime('now', '-7 days'))
                .order_by(desc(DownloadCatalog.last_updated))
                .limit(20)
            )
            nw_rows = (await db.execute(nw_stmt)).scalars().all()
            if nw_rows and len(nw_rows) >= 3:
                rows.append({
                    "type": "row",
                    "title": "New This Week",
                    "items": [_serialize_catalog_entry(c) for c in nw_rows],
                })

            # ── New This Month ──
            nm_stmt = (
                select(DownloadCatalog)
                .where(DownloadCatalog.last_updated >= func.datetime('now', '-30 days'))
                .order_by(desc(DownloadCatalog.last_updated))
                .limit(20)
            )
            nm_rows = (await db.execute(nm_stmt)).scalars().all()
            if nm_rows and len(nm_rows) >= 3:
                rows.append({
                    "type": "row",
                    "title": "New This Month",
                    "items": [_serialize_catalog_entry(c) for c in nm_rows],
                })

            # ── Newly Trending ──
            if user:
                trending_sub = (
                    select(WatchHistory.media_path, func.count(WatchHistory.id).label('cnt'))
                    .where(WatchHistory.last_watched >= func.datetime('now', '-14 days'))
                    .group_by(WatchHistory.media_path)
                    .order_by(desc('cnt'))
                    .limit(50)
                ).subquery()
                trending_codes = set()
                for c in (await db.execute(trending_sub)).all():
                    p = Path(c.media_path)
                    try:
                        match = (await db.execute(
                            select(DownloadCatalog).where(DownloadCatalog.title.ilike(f"%{p.stem[:30]}%")).limit(1)
                        )).scalar_one_or_none()
                        if match:
                            trending_codes.add(match.imdb_code)
                    except Exception:
                        pass
                if trending_codes:
                    trend_stmt = (
                        select(DownloadCatalog)
                        .where(DownloadCatalog.imdb_code.in_(list(trending_codes)))
                        .order_by(desc(DownloadCatalog.imdb_rating))
                        .limit(20)
                    )
                    trend_rows = (await db.execute(trend_stmt)).scalars().all()
                    if trend_rows and len(trend_rows) >= 3:
                        rows.append({
                            "type": "row",
                            "title": "Newly Trending",
                            "items": [_serialize_catalog_entry(c) for c in trend_rows],
                        })

            # ── Recommended For You ──
            if user:
                fav_codes = set()
                fav_stmt = select(CatalogFavorite.catalog_id).where(CatalogFavorite.user_id == user.id).limit(20)
                fav_ids = [r[0] for r in (await db.execute(fav_stmt)).all() if r[0]]
                if fav_ids:
                    fav_entries = (await db.execute(
                        select(DownloadCatalog).where(DownloadCatalog.id.in_(fav_ids))
                    )).scalars().all()
                    fav_genres = set()
                    fav_cast = set()
                    for e in fav_entries:
                        try:
                            for g in json.loads(e.genres_json or "[]"):
                                fav_genres.add(g)
                        except Exception:
                            pass
                        try:
                            for act in json.loads(e.cast_json or "[]"):
                                if isinstance(act, dict) and act.get("name"):
                                    fav_cast.add(act["name"])
                        except Exception:
                            pass
                    if fav_genres or fav_cast:
                        rec_candidates = (await db.execute(
                            select(DownloadCatalog).where(
                                DownloadCatalog.genres_json != "[]",
                                DownloadCatalog.id.notin_(fav_ids) if fav_ids else True,
                            ).limit(200)
                        )).scalars().all()
                        scored = []
                        for e in rec_candidates:
                            score = 0
                            try:
                                eg = set(json.loads(e.genres_json or "[]"))
                                score += len(eg & fav_genres) * 2
                            except Exception:
                                eg = set()
                            try:
                                ec = set()
                                for act in json.loads(e.cast_json or "[]"):
                                    if isinstance(act, dict) and act.get("name"):
                                        ec.add(act["name"])
                                score += len(ec & fav_cast)
                            except Exception:
                                pass
                            if score > 0:
                                scored.append((score, e))
                        scored.sort(key=lambda x: -x[0])
                        rec_items = [_serialize_catalog_entry(e) for _, e in scored[:20]]
                        if len(rec_items) >= 3:
                            rows.append({
                                "type": "row",
                                "title": "Recommended For You",
                                "items": rec_items,
                            })

        # ── TMDB rows (only if configured) ──
        if tmdb.is_configured():
            trending = await _tmdb_trending("movie")
            if trending:
                rows.append({
                    "type": "row",
                    "title": "Trending on TMDB",
                    "items": trending,
                    "tmdb": True,
                })
            popular_tv = await _tmdb_trending("tv")
            if popular_tv:
                rows.append({
                    "type": "row",
                    "title": "Popular TV Shows",
                    "items": popular_tv,
                    "tmdb": True,
                })
    except Exception as e:
        logger.warning(f"library_rows failed: {e}")

    logger.debug("Library rows result: %d rows for user=%s", len(rows), user.username if user else "anonymous")
    resp = {"success": True, "rows": rows}
    response_cache.set(cache_key, resp, ttl=60)
    return resp


async def _tmdb_trending(media_type: str) -> List[Dict[str, Any]]:
    """Pull a small list of trending items from TMDB."""
    if not tmdb.is_configured():
        return []
    try:
        data = await tmdb._request(f"/trending/{media_type}/week")
        if not data:
            return []
        # Load catalog IDs/titles for matching TMDB items to local covers
        matched_ids = {}
        try:
            async with async_session() as db:
                stmt = select(DownloadCatalog.id, DownloadCatalog.title, DownloadCatalog.year, DownloadCatalog.imdb_code, DownloadCatalog.cover_url)
                rows = (await db.execute(stmt)).all()
                for r in rows:
                    key = (r.title.strip().lower() if r.title else '', str(r.year or ''))
                    matched_ids[key] = (r.imdb_code, r.cover_url)
        except Exception:
            logger.debug("TMDB trending — catalog lookup failed, continuing without local covers")
        out = []
        for r in (data.get("results") or [])[:20]:
            if media_type == "movie":
                t = r.get("title") or r.get("original_title")
                y = (r.get("release_date") or "")[:4]
            else:
                t = r.get("name") or r.get("original_name")
                y = (r.get("first_air_date") or "")[:4]
            match = matched_ids.get((t.strip().lower() if t else '', y))
            imdb_code = match[0] if match else None
            cover_url = match[1] if match else None
            out.append({
                "tmdb_id": r.get("id"),
                "title": t,
                "year": y,
                "rating": r.get("vote_average", 0),
                "overview": r.get("overview", ""),
                "poster_url": tmdb._img(r.get("poster_path"), "w500"),
                "backdrop_url": tmdb._img(r.get("backdrop_path"), "w1280"),
                "cover_url": cover_url,
                "imdb_code": imdb_code,
                "type": media_type,
                "genres": [],
                "cast": [],
            })
        return out
    except Exception as e:
        logger.debug(f"TMDB trending failed: {e}")
        return []


@router.get("/search")
async def library_search(
    q: str = Query("", min_length=1),
    limit: int = Query(30),
    user: Optional[User] = Depends(get_optional_user),
):
    """Search the local catalog by title, year, genre, cast, director, type."""
    q = q.strip()
    if not q:
        logger.debug("Library search - empty query")
        return {"success": True, "results": []}
    logger.debug("Library search: q=%s limit=%d user=%s", q, limit, user.username if user else "anonymous")
    cache_key = f"library:search:{q.lower()}:{limit}"
    cached = response_cache.get(cache_key)
    if cached:
        return cached
    try:
        async with async_session() as db:
            # Search across title, year, cast, director, overview, and title_type
            stmt = select(DownloadCatalog).where(
                (DownloadCatalog.title.ilike(f"%{q}%")) |
                (DownloadCatalog.year.ilike(f"%{q}%")) |
                (DownloadCatalog.cast_json.ilike(f"%{q}%")) |
                (DownloadCatalog.director.ilike(f"%{q}%")) |
                (DownloadCatalog.overview.ilike(f"%{q}%")) |
                (DownloadCatalog.title_type.ilike(f"%{q}%")) |
                (DownloadCatalog.genres_json.ilike(f"%{q}%"))
            ).limit(limit)
            rows = (await db.execute(stmt)).scalars().all()
            results = [_serialize_catalog_entry(c) for c in rows]
        logger.debug("Library search results: q=%s count=%d", q, len(results))
        resp = {"success": True, "results": results}
        response_cache.set(cache_key, resp, ttl=30)
        return resp
    except Exception as e:
        logger.warning(f"library_search failed: {e}")
        return {"success": False, "detail": str(e)}


@router.get("/genre/{genre}")
async def library_by_genre(
    genre: str,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=50),
    user: Optional[User] = Depends(get_optional_user),
):
    """Get all entries that include a particular genre."""
    logger.debug("Library by genre: genre=%s page=%d per_page=%d", genre, page, per_page)
    cache_key = f"library:genre:{genre.lower()}:{page}:{per_page}"
    cached = response_cache.get(cache_key)
    if cached:
        return cached
    try:
        async with async_session() as db:
            like = f'%"{genre}"%'
            stmt = select(DownloadCatalog).where(
                DownloadCatalog.genres_json.ilike(like)
            ).order_by(desc(cast(DownloadCatalog.imdb_rating, Float)))
            rows = (await db.execute(stmt)).scalars().all()
            total = len(rows)
            start = (page - 1) * per_page
            items = [_serialize_catalog_entry(c) for c in rows[start:start + per_page]]
        resp = {
            "success": True,
            "genre": genre,
            "items": items,
            "page": page,
            "has_more": start + per_page < total,
        }
        response_cache.set(cache_key, resp, ttl=60)
        return resp
    except Exception as e:
        logger.warning(f"library_by_genre failed: {e}")
        return {"success": False, "detail": str(e)}


@router.get("/genres")
async def library_genres():
    """List all distinct genres present in the catalog with entry counts."""
    logger.debug("List all genres")
    cache_key = "library:genres"
    cached = response_cache.get(cache_key)
    if cached:
        return cached
    counts: Dict[str, int] = {}
    try:
        async with async_session() as db:
            rows = (await db.execute(select(DownloadCatalog.genres_json))).all()
            for (g,) in rows:
                try:
                    gs = json.loads(g or "[]")
                except Exception:
                    gs = []
                for x in gs:
                    counts[x] = counts.get(x, 0) + 1
    except Exception as e:
        logger.warning(f"library_genres failed: {e}")
    items = [{"name": k, "count": v} for k, v in sorted(counts.items(), key=lambda kv: -kv[1])]
    resp = {"success": True, "genres": items}
    response_cache.set(cache_key, resp, ttl=60)
    return resp


@router.get("/detail/{catalog_id}")
async def library_detail(
    catalog_id: int,
    user: Optional[User] = Depends(get_optional_user),
):
    """Full detail for the Netflix-style detail overlay.

    Includes the catalog entry, related catalog items by genre, and
    TMDB recommendations if a TMDB key is configured.
    """
    logger.debug("Library detail: catalog_id=%d user=%s", catalog_id, user.username if user else "anonymous")
    try:
        async with async_session() as db:
            result = await db.execute(select(DownloadCatalog).where(DownloadCatalog.id == catalog_id))
            entry = result.scalar_one_or_none()
            if not entry:
                logger.warning("Library detail not found: catalog_id=%d", catalog_id)
                return {"success": False, "detail": "Not found"}
            data = _serialize_catalog_entry(entry)

            # Related: same genres, excluding self
            related = []
            try:
                genres = json.loads(entry.genres_json or "[]")
            except Exception:
                genres = []
            if genres:
                rel_stmt = select(DownloadCatalog).where(
                    DownloadCatalog.id != entry.id,
                    DownloadCatalog.genres_json != "[]",
                ).order_by(desc(cast(DownloadCatalog.imdb_rating, Float))).limit(30)
                rel_rows = (await db.execute(rel_stmt)).scalars().all()
                for r in rel_rows:
                    try:
                        rg = json.loads(r.genres_json or "[]")
                    except Exception:
                        rg = []
                    if any(g in rg for g in genres):
                        related.append(_serialize_catalog_entry(r))
                        if len(related) >= 12:
                            break
            data["related"] = related
        # TMDB recs (optional)
        if tmdb.is_configured() and entry.imdb_code:
            try:
                recs = await tmdb.get_recommendations(entry.imdb_code, limit=10)
                data["tmdb_recommendations"] = recs
            except Exception:
                data["tmdb_recommendations"] = []
        else:
            data["tmdb_recommendations"] = []
        return {"success": True, "entry": data}
    except Exception as e:
        logger.warning(f"library_detail failed: {e}")
        return {"success": False, "detail": str(e)}


@router.get("/continue-watching")
async def get_continue_watching(user: Optional[User] = Depends(get_optional_user)):
    logger.debug("Get continue watching: user=%s", user.username if user else "anonymous")
    if not user:
        return {"success": True, "items": []}
    try:
        async with async_session() as db:
            result = await db.execute(
                select(WatchHistory)
                .where(WatchHistory.user_id == user.id)
                .order_by(desc(WatchHistory.last_watched))
                .limit(20)
            )
            history_items = result.scalars().all()
        items = []
        for h in history_items:
            p = Path(h.media_path)
            if not p.exists():
                continue
            duration = h.duration_sec or 0
            progress_pct = round((h.position_sec / duration * 100), 1) if duration > 0 else 0
            items.append({
                "name": p.name,
                "path": str(p),
                "position": h.position_sec,
                "duration": duration,
                "progress_pct": progress_pct,
                "updated_at": h.last_watched.isoformat() if h.last_watched else None,
            })
        return {"success": True, "items": items}
    except Exception as e:
        logger.warning(f"Continue-watching failed: {e}")
        return {"success": True, "items": []}


@router.get("/watchlist")
async def get_watchlist(
    status: Optional[str] = Query(None),
    user: User = Depends(get_current_user),
):
    logger.debug("Get watchlist: user=%s status=%s", user.username, status)
    try:
        async with async_session() as db:
            query = (
                select(CatalogFavorite, DownloadCatalog)
                .join(DownloadCatalog, CatalogFavorite.catalog_id == DownloadCatalog.id)
                .where(CatalogFavorite.user_id == user.id)
            )
            if status and status != "all":
                query = query.where(CatalogFavorite.status == status)
            query = query.order_by(desc(CatalogFavorite.created_at))
            result = await db.execute(query)
            rows = result.all()
        items = []
        for fav, cat in rows:
            items.append({
                "id": fav.id,
                "catalog_id": cat.id,
                "title": cat.title,
                "year": cat.year,
                "imdb_rating": cat.imdb_rating,
                "cover_url": cat.cover_url,
                "backdrop_url": cat.backdrop_url,
                "overview": cat.overview,
                "status": getattr(fav, "status", "want_to_watch"),
                "created_at": fav.created_at.isoformat() if fav.created_at else None,
            })
        return {"success": True, "items": items}
    except Exception as e:
        logger.warning(f"Watchlist fetch failed: {e}")
        return {"success": True, "items": []}


@router.post("/watchlist/{catalog_id}")
async def add_to_watchlist(
    catalog_id: int,
    user: User = Depends(get_current_user),
):
    logger.info("Add to watchlist: catalog_id=%d user=%s", catalog_id, user.username)
    try:
        async with async_session() as db:
            existing = await db.execute(
                select(CatalogFavorite).where(
                    CatalogFavorite.user_id == user.id,
                    CatalogFavorite.catalog_id == catalog_id,
                )
            )
            if existing.scalar_one_or_none():
                logger.debug("Already in watchlist: catalog_id=%d user=%s", catalog_id, user.username)
                return {"success": True, "detail": "Already in watchlist"}
            fav = CatalogFavorite(user_id=user.id, catalog_id=catalog_id)
            db.add(fav)
            await db.commit()
        return {"success": True, "detail": "Added to watchlist"}
    except Exception as e:
        return {"success": False, "detail": str(e)}


@router.delete("/watchlist/{catalog_id}")
async def remove_from_watchlist(
    catalog_id: int,
    user: User = Depends(get_current_user),
):
    logger.info("Remove from watchlist: catalog_id=%d user=%s", catalog_id, user.username)
    try:
        async with async_session() as db:
            result = await db.execute(
                select(CatalogFavorite).where(
                    CatalogFavorite.user_id == user.id,
                    CatalogFavorite.catalog_id == catalog_id,
                )
            )
            fav = result.scalar_one_or_none()
            if fav:
                await db.delete(fav)
                await db.commit()
                logger.info("Watchlist item removed: catalog_id=%d user=%s", catalog_id, user.username)
        return {"success": True, "detail": "Removed from watchlist"}
    except Exception as e:
        return {"success": False, "detail": str(e)}


@router.post("/watchlist/{catalog_id}/status")
async def update_watchlist_status(
    catalog_id: int,
    status: str = Query(..., description="want_to_watch, watching, completed, dropped"),
    user: User = Depends(get_current_user),
):
    logger.info("Update watchlist status: catalog_id=%d status=%s user=%s", catalog_id, status, user.username)
    valid = {"want_to_watch", "watching", "completed", "dropped"}
    if status not in valid:
        logger.warning("Invalid watchlist status: %s user=%s", status, user.username)
        return {"success": False, "detail": f"Invalid status. Use: {', '.join(valid)}"}
    try:
        async with async_session() as db:
            result = await db.execute(
                select(CatalogFavorite).where(
                    CatalogFavorite.user_id == user.id,
                    CatalogFavorite.catalog_id == catalog_id,
                )
            )
            fav = result.scalar_one_or_none()
            if not fav:
                return {"success": False, "detail": "Item not in watchlist"}
            fav.status = status
            await db.commit()
        return {"success": True, "status": status}
    except Exception as e:
        return {"success": False, "detail": str(e)}


def _extract_quality_options(links_json: str) -> List[Dict[str, Any]]:
    """Parse a *_links JSON column into a list of {label, url, size} options."""
    try:
        links = json.loads(links_json or "[]")
    except Exception:
        return []
    out = []
    for l in links:
        if not isinstance(l, dict):
            continue
        label = l.get("label") or l.get("quality") or l.get("url", "").rsplit("/", 1)[-1]
        out.append({
            "label": str(label),
            "url": l.get("url", ""),
            "size": l.get("size", ""),
        })
    return out


def _derive_subtitle_type_from_url(url: str) -> str:
    """Extract subtitle type (SoftSub/Dubbed/NoSub) from a URL path."""
    parts = url.rstrip("/").split("/")
    for part in reversed(parts):
        pl = part.lower()
        if "softsub" in pl or "subtitle" in pl:
            return "softsub"
        if "dubbed" in pl or "dub" in pl:
            return "dubbed"
        if "nosub" in pl or "nosubtitle" in pl:
            return "nosub"
    return "softsub"


def _derive_quality_from_url(url: str) -> str:
    """Extract quality label (1080p/720p/etc.) from a URL path."""
    parts = url.rstrip("/").split("/")
    for part in reversed(parts):
        pl = part.lower()
        if "1080" in pl or "1080p" in pl:
            return "1080p"
        if "720" in pl or "720p" in pl:
            return "720p"
        if "480" in pl or "480p" in pl:
            return "480p"
    return "HD"


@router.get("/queue-options/{catalog_id}")
async def queue_options(
    catalog_id: int,
    user: User = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
):
    """Return available quality / subtitle / season options for a catalog entry.

    Used by the library detail modal to populate the "Add to Queue" form.
    Returns:
      {
        success, id, imdb_code, title, year, title_type, is_series,
        subtitle_types: [
          {key: "SoftSub", label: "SoftSub (Subtitle)", options: [{label, url, size}, ...]},
          ...
        ],
        seasons: {  # only for series
          "Season 1": {label, url, ...},
          "ALL": {...},
        }
      }
    """
    logger.debug("Queue options: catalog_id=%d user=%s", catalog_id, user.username if user else "anonymous")
    result = await db.execute(select(DownloadCatalog).where(DownloadCatalog.id == catalog_id))
    entry = result.scalar_one_or_none()
    if not entry:
        logger.warning("Queue options - catalog not found: %d", catalog_id)
        return {"success": False, "detail": "Catalog entry not found"}

    is_series = (entry.title_type or "movie") != "movie" or bool(entry.has_seasons)

    subtitle_types = []
    if is_series:
        # For series: derive subtitle types from season URLs
        try:
            season_info = json.loads(entry.season_info or "{}")
        except Exception:
            season_info = {}
        seen_stypes: Dict[str, str] = {}
        for sname, eps in season_info.items():
            if not isinstance(eps, list):
                continue
            for ep in eps:
                url = ep.get("url", "") if isinstance(ep, dict) else ""
                if url:
                    st = _derive_subtitle_type_from_url(url)
                    if st not in seen_stypes:
                        seen_stypes[st] = url
        for st_key, sample_url in seen_stypes.items():
            labels_map: Dict[str, dict] = {}
            for sname, eps in season_info.items():
                if not isinstance(eps, list):
                    continue
                for ep in eps:
                    url = ep.get("url", "") if isinstance(ep, dict) else ""
                    if not url:
                        continue
                    if _derive_subtitle_type_from_url(url) != st_key:
                        continue
                    qlabel = _derive_quality_from_url(url)
                    if qlabel not in labels_map:
                        labels_map[qlabel] = {"label": qlabel, "url": url, "size": ""}
            options = list(labels_map.values())
            if not options:
                # Fallback: one option per season using the sample URL
                options = [{"label": "All Episodes", "url": sample_url, "size": ""}]
            label_map = {"softsub": "SoftSub (Subtitle)", "dubbed": "Dubbed", "nosub": "NoSub"}
            subtitle_types.append({"key": st_key, "label": label_map.get(st_key, st_key), "options": options})
    else:
        for key, label in [("softsub", "SoftSub (Subtitle)"), ("dubbed", "Dubbed"), ("nosub", "NoSub")]:
            col = getattr(entry, f"{key}_links", "[]")
            options = _extract_quality_options(col)
            if options:
                subtitle_types.append({"key": key, "label": label, "options": options})

    seasons: Dict[str, Any] = {}
    if is_series:
        try:
            season_info = json.loads(entry.season_info or "{}")
        except Exception:
            season_info = {}
        if isinstance(season_info, dict):
            for season_name, eps in season_info.items():
                if not isinstance(eps, list) or not eps:
                    continue
                # The first link in the season is the season page URL
                first = eps[0] if isinstance(eps[0], dict) else {}
                seasons[str(season_name)] = {
                    "label": str(season_name),
                    "url": first.get("url", ""),
                    "episode_count": len(eps),
                }

    return {
        "success": True,
        "id": entry.id,
        "imdb_code": entry.imdb_code,
        "title": entry.title,
        "year": entry.year,
        "title_type": entry.title_type or "movie",
        "is_series": is_series,
        "has_seasons": bool(entry.has_seasons),
        "subtitle_types": subtitle_types,
        "seasons": seasons,
    }


@router.get("/season-episodes")
async def season_episodes(
    url: str = Query(""),
    user: User = Depends(get_optional_user),
):
    """Fetch a season page and return the list of episode .mkv files.
    Used by the Add to Queue modal to populate the episode picker.
    """
    logger.debug("Season episodes: url=%s user=%s", url[:80], user.username if user else "anonymous")
    if not url:
        logger.warning("Season episodes - URL required")
        return {"success": False, "detail": "URL required", "episodes": []}
    from app.services.scraper import fetch_season_page
    import urllib.parse
    season_files = await fetch_season_page(url)
    if not season_files:
        return {"success": False, "detail": "Could not parse season page", "episodes": []}
    mkv_files = [f for f in season_files if f["name"].lower().endswith(".mkv")]
    return {
        "success": True,
        "episodes": [
            {
                "name": f["name"],
                "url": urllib.parse.urljoin(url.rstrip("/") + "/", f["url"]),
                "size": f.get("size", ""),
            }
            for f in mkv_files
        ],
        "count": len(mkv_files),
    }
