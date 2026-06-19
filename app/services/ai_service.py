from __future__ import annotations
import logging
from typing import Any

from app.services import local_ai

logger = logging.getLogger(__name__)


async def categorize_media(
    title: str,
    filename: str,
    genre_hints: list[str] | None = None,
) -> dict[str, Any]:
    return await local_ai.categorize_media(title, filename, genre_hints)


async def recommend_media(
    recently_watched: list[str],
    available_titles: list[str],
) -> list[dict[str, Any]]:
    return await local_ai.recommend_media(recently_watched, available_titles)


async def enrich_metadata(
    title: str,
    filename: str,
    existing_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return await local_ai.enrich_metadata(title, filename, existing_metadata)
