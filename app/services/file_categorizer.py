import json
import logging
import os
import re
from pathlib import Path
from typing import Optional

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.file_category import FileCategory
from app.services.ai_service import categorize_media

logger = logging.getLogger(__name__)

MEDIA_EXTENSIONS = {".mp4", ".mkv", ".webm", ".avi", ".mov", ".m4v", ".flv", ".wmv", ".mp3", ".wav", ".aac", ".flac", ".m4a", ".ogg"}

# Local heuristic patterns for offline categorization (no API needed)
_EPISODE_PATTERNS = [
    re.compile(r"S\d{1,2}E\d{1,3}", re.IGNORECASE),         # S01E01
    re.compile(r"S\d{1,2}\s*E\d{1,3}", re.IGNORECASE),      # S01 E01
    re.compile(r"Episode[\s._-]*\d+", re.IGNORECASE),       # Episode.1, Episode_1
    re.compile(r"Ep[\s._-]*\d{1,3}", re.IGNORECASE),        # Ep.1, Ep_1
    re.compile(r"\d{1,2}x\d{2}"),                            # 1x01
    re.compile(r"Season[\s._-]*\d+", re.IGNORECASE),        # Season.1
    re.compile(r"Complete|Series"),                          # series markers
]
_GENRE_HINTS = {
    "anime": [r"\banime\b", r"\b\d{2,3}\s*episodes?\b", r"\[(BD|DVD|Web)\]", r"\b(Subbed|Dubbed)\b"],
    "documentary": [r"\bdocumentary\b", r"\bdocu\b", r"discovery", r"national\s*geo", r"bbc", r"history\s*channel"],
    "concert": [r"\bconcert\b", r"\blive\b", r"\btour\b", r"\.live\.", r"\bunplugged\b"],
    "kids": [r"\bkids?\b", r"\bcartoon\b", r"\banimation\b", r"\bdisney\b", r"pixar"],
}


def _local_categorize(filepath: str) -> dict:
    """Heuristic-based categorization that works without an API."""
    fname = os.path.basename(filepath)
    stem = Path(filepath).stem
    parent_path = str(Path(filepath).parent).lower().replace("\\", "/")
    lower = (fname + " " + stem + " " + parent_path).lower()

    # Detect series
    is_series = any(p.search(fname) for p in _EPISODE_PATTERNS)
    # Check parent directory: if 'series' or 'tv' or 'shows' in path
    if any(seg in parent_path for seg in ["/series", "/tv_shows", "/tv/", "/shows/"]):
        is_series = True

    # Detect genre (from filename + parent directory)
    genres = []
    category = "series" if is_series else "movie"
    for genre, patterns in _GENRE_HINTS.items():
        if any(re.search(p, lower) for p in patterns):
            genres.append(genre)
            if genre == "anime":
                category = "anime"
            elif genre == "documentary":
                category = "documentary"
            elif genre == "concert":
                category = "concert"
            elif genre == "kids":
                genres.append("animation")
                category = "movie"

    # Extract year (4 digits 1900-2099)
    year_match = re.search(r"\b(19\d{2}|20\d{2})\b", fname)
    year = int(year_match.group(1)) if year_match else None

    # Clean title
    title = re.sub(r"\.|\(.*?\)|\[.*?\]", " ", stem)
    title = re.sub(
        r"\b(19|20)\d{2}\b|\bS\d{1,2}E\d{1,3}\b|\bS\d{1,2}\b|"
        r"\bSeason[\s._-]*\d+\b|\bEpisode[\s._-]*\d+\b|"
        r"1080p|720p|480p|2160p|4K|BluRay|BRRip|WEB[-_.]?DL|HDRip|"
        r"x26[45]|x21[6]|HEVC|AAC|BD|DVD|IMAX|Complete|Series|MULTi",
        "", title, flags=re.IGNORECASE)
    title = re.sub(r"\s+", " ", title).strip()

    return {
        "title": title or stem,
        "category": category,
        "genre": genres,
        "year": year,
        "confidence": 0.5,  # local heuristics — lower confidence
    }


def _get_filename_stem(filepath: str) -> str:
    return Path(filepath).stem


def _is_media_file(name: str) -> bool:
    ext = Path(name).suffix.lower()
    return ext in MEDIA_EXTENSIONS


async def categorize_file(db: AsyncSession, file_path: str, media_root: str) -> Optional[dict]:
    full_path = os.path.join(media_root, file_path)
    if not os.path.isfile(full_path):
        return None
    fname = os.path.basename(file_path)
    title = _get_filename_stem(file_path)

    # Try AI first, fall back to local heuristics
    result = None
    try:
        result = await categorize_media(title, fname)
    except Exception as e:
        logger.debug(f"AI categorize failed for {file_path}: {e}")

    # If AI failed or low confidence, use local heuristics
    if not result or result.get("error") or result.get("confidence", 0) < 0.3:
        local_result = _local_categorize(file_path)
        if result and result.get("confidence", 0) > 0.0:
            # Merge: keep AI's better fields where available
            for k in ("title", "category", "genre", "year"):
                ai_val = result.get(k)
                local_val = local_result.get(k)
                if ai_val and (not local_val or (isinstance(ai_val, list) and len(ai_val) > len(local_val))):
                    pass  # keep AI
                elif local_val and not ai_val:
                    result[k] = local_val
            if result.get("confidence", 0) < 0.3:
                result["confidence"] = local_result["confidence"]
        else:
            result = local_result

    if not result:
        return None

    if result.get("error"):
        return None

    genre_json = json.dumps(result.get("genre", []), ensure_ascii=False)
    await db.merge(
        FileCategory(
            file_path=file_path,
            category=result.get("category", "other"),
            genre=genre_json,
            year=result.get("year"),
            confidence=result.get("confidence", 0),
        )
    )
    await db.commit()
    return result


async def batch_categorize_files(db: AsyncSession, media_root: str, limit: int = 100) -> int:
    existing_result = await db.execute(select(FileCategory.file_path))
    categorized = {row[0] for row in existing_result.all()}

    candidates = []
    for root, _dirs, fnames in os.walk(media_root):
        for fname in fnames:
            if not _is_media_file(fname):
                continue
            rel = os.path.relpath(os.path.join(root, fname), media_root).replace("\\", "/")
            if rel not in categorized:
                candidates.append(rel)
        if len(candidates) >= limit:
            break

    if not candidates:
        return 0

    done = 0
    skipped = 0
    errors = 0
    for rel_path in candidates:
        try:
            ok = await categorize_file(db, rel_path, media_root)
            if ok:
                done += 1
            else:
                skipped += 1
        except Exception as e:
            errors += 1
            logger.warning(f"Unexpected error categorizing {rel_path}: {e}")

    logger.info(f"Batch categorize: {done} categorized, {skipped} skipped, {errors} errors (of {len(candidates)} candidates)")
    return done


async def get_categories_for_paths(db: AsyncSession, paths: list[str]) -> dict:
    if not paths:
        return {}
    result = await db.execute(select(FileCategory).where(FileCategory.file_path.in_(paths)))
    rows = result.scalars().all()
    out = {}
    for row in rows:
        genre = []
        try:
            genre = json.loads(row.genre) if row.genre else []
        except (json.JSONDecodeError, TypeError):
            genre = []
        out[row.file_path] = {
            "category": row.category,
            "genre": genre,
            "year": row.year,
            "confidence": row.confidence,
        }
    return out
