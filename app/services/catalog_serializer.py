"""Shared serialization for DownloadCatalog entries.

Used by library.py, catalog.py, and any other module that needs
to convert a DownloadCatalog row into a JSON-serializable dict.
"""
import json
from typing import Dict, Any

from app.models.download_catalog import DownloadCatalog


def serialize_catalog_entry(c: DownloadCatalog) -> Dict[str, Any]:
    """Serialize a DownloadCatalog row into a uniform shape for the UI."""
    try:
        genres = json.loads(c.genres_json or "[]")
    except Exception:
        genres = []
    try:
        cast_list = json.loads(c.cast_json or "[]")
    except Exception:
        cast_list = []
    return {
        "id": c.id,
        "imdb_code": c.imdb_code,
        "title": c.title,
        "year": c.year,
        "title_type": c.title_type or "movie",
        "imdb_rating": c.imdb_rating,
        "imdb_votes": c.imdb_votes,
        "cover_url": c.cover_url,
        "backdrop_url": c.backdrop_url,
        "overview": c.overview,
        "tagline": c.tagline,
        "genres": genres,
        "cast": cast_list,
        "director": c.director,
        "runtime_min": c.runtime_min,
        "has_seasons": c.has_seasons,
    }


def serialize_catalog_brief(c: DownloadCatalog) -> Dict[str, Any]:
    """Lightweight serialization for list/grid views (no overview/cast)."""
    return {
        "id": c.id,
        "imdb_code": c.imdb_code,
        "title": c.title,
        "year": c.year,
        "title_type": c.title_type or "movie",
        "imdb_rating": c.imdb_rating,
        "imdb_votes": c.imdb_votes,
        "has_seasons": c.has_seasons,
        "cover_url": c.cover_url,
    }
