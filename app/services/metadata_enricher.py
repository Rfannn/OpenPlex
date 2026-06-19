from __future__ import annotations
import logging
from pathlib import Path
from typing import Optional

from app.services.local_ai import search_metadata

logger = logging.getLogger(__name__)


def _clean_title(filename: str) -> str:
    import re
    name = Path(filename).stem
    name = re.sub(r"[-_.]", " ", name)
    name = re.sub(r"\b\d{3,4}p\b|\bbluray\b|\bweb[ -]?dl\b|\bhdtv\b|\bx264\b|\bx265\b|\bh265\b|\baac\b|\bmp4\b|\bmkv\b|\bavi\b", "", name, flags=re.IGNORECASE)
    name = re.sub(r"\bS\d{1,2}\b|\bE\d{1,2}\b|\bSeason\s+\d+\b|\bEpisode\s+\d+\b", "", name, flags=re.IGNORECASE)
    name = re.sub(r"\(?\d{4}\)?", "", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name[:100]


async def enrich_media_by_filename(filename: str) -> dict:
    title = _clean_title(filename)
    if not title or len(title) < 2:
        return {}

    result = await search_metadata(title)
    if result:
        return {
            "poster_url": "",
            "title": result.get("title", title),
            "year": result.get("year"),
            "genre": result.get("genre", []),
            "imdb_rating": "",
            "synopsis": result.get("synopsis", ""),
            "source": "local_ai",
        }

    return {}
