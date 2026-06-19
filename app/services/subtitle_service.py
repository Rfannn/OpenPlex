import httpx
import os
import zipfile
import tempfile
import shutil
import logging
from typing import Optional

from app.services import opensubtitles

logger = logging.getLogger(__name__)

SUB_PLUS_API = "https://sub-plus.ir/api.php"

SUBTITLE_EXTS = {".srt", ".ass", ".ssa", ".sub", ".vtt"}

# ── sub-plus.ir ──

async def search_subtitles(query: str, language: str = "English") -> list:
    logger.debug(f"search_subtitles entry: query={query!r}, language={language!r}")
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(SUB_PLUS_API, data={"q": query, "l": language})
            data = r.json()
            if data.get("ok") and data.get("count", 0) > 0:
                results = data["result"]
                logger.debug(f"search_subtitles: found {len(results)} results from sub-plus")
                return results
            logger.debug(f"search_subtitles: no results from sub-plus for query={query!r}")
            return []
    except Exception as e:
        logger.warning(f"search_subtitles failed for query={query!r}: {e}")
        return []

async def get_download_link(tag: str) -> Optional[str]:
    logger.debug(f"get_download_link entry: tag={tag!r}")
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(SUB_PLUS_API, data={"dl": tag})
            data = r.json()
            if data.get("ok") and data.get("download"):
                url = data["download"]
                logger.debug(f"get_download_link: got url={url!r} for tag={tag!r}")
                return url
            logger.debug(f"get_download_link: no download link for tag={tag!r}")
            return None
    except Exception as e:
        logger.warning(f"get_download_link failed for tag={tag!r}: {e}")
        return None

async def download_and_extract(url: str, dest_dir: str) -> list[str]:
    logger.debug(f"download_and_extract entry: url={url!r}, dest_dir={dest_dir!r}")
    saved = []
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(url)
            r.raise_for_status()
            content = r.content
        ext = os.path.splitext(url.split("/")[-1])[1].lower()
        if ext == ".zip":
            with tempfile.TemporaryDirectory() as tmp:
                zip_path = os.path.join(tmp, "subs.zip")
                with open(zip_path, "wb") as f:
                    f.write(content)
                with zipfile.ZipFile(zip_path, "r") as zf:
                    zf.extractall(tmp)
                for fname in os.listdir(tmp):
                    if os.path.splitext(fname)[1].lower() in SUBTITLE_EXTS:
                        src = os.path.join(tmp, fname)
                        dst = os.path.join(dest_dir, fname)
                        if not os.path.exists(dst):
                            shutil.copy2(src, dst)
                            saved.append(dst)
                            logger.debug(f"download_and_extract: extracted {dst}")
        elif ext in SUBTITLE_EXTS:
            fname = url.split("/")[-1]
            dst = os.path.join(dest_dir, fname)
            if not os.path.exists(dst):
                with open(dst, "wb") as f:
                    f.write(content)
                saved.append(dst)
                logger.debug(f"download_and_extract: saved direct file {dst}")
        logger.debug(f"download_and_extract: saved {len(saved)} subtitle file(s)")
        return saved
    except Exception as e:
        logger.warning(f"download_and_extract failed: {e}")
        return saved

# ── OpenSubtitles ──

async def search_subtitles_opensubs(query: str, imdb_id: str = "") -> list:
    """Search OpenSubtitles for subtitles. Returns list compatible with player UI."""
    logger.debug(f"search_subtitles_opensubs entry: query={query!r}, imdb_id={imdb_id!r}")
    try:
        results = await opensubtitles.search(query=query, imdb_id=imdb_id)
        out = []
        for r in results:
            lang = r.get("language", "Unknown")
            fmt = (r.get("format") or "srt").upper()
            info_parts = [lang, fmt]
            if r.get("downloads"):
                info_parts.append(f"{r['downloads']} DLs")
            out.append({
                "tag": f"opensub:{r.get('id')}:{r['files'][0]['id']}" if r.get("files") else f"opensub:{r.get('id')}",
                "source": "opensubtitles",
                "title": r.get("name", ""),
                "info": " • ".join(info_parts),
                "series": False,
            })
        logger.debug(f"search_subtitles_opensubs: found {len(out)} results from OpenSubtitles")
        return out
    except Exception as e:
        logger.warning(f"search_subtitles_opensubs failed: {e}")
        return []


async def download_opensubtitle(tag: str, dest_dir: str) -> list[str]:
    """Download subtitle from OpenSubtitles by tag (format: opensub:{sub_id}:{file_id})."""
    logger.debug(f"download_opensubtitle entry: tag={tag!r}, dest_dir={dest_dir!r}")
    try:
        parts = tag.split(":")
        if len(parts) < 2:
            logger.warning(f"download_opensubtitle: invalid tag format {tag!r}")
            return []
        sub_id = parts[1]
        file_id = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else None
        if not file_id:
            logger.warning(f"download_opensubtitle: no valid file_id in tag {tag!r}")
            return []
        content = await opensubtitles.download(file_id)
        if not content:
            logger.warning(f"download_opensubtitle: empty content for file_id={file_id}")
            return []
        # Save as .srt (OpenSubtitles usually returns .srt or .vtt)
        fname = f"{sub_id}.srt"
        dst = os.path.join(dest_dir, fname)
        if not os.path.exists(dst):
            with open(dst, "wb") as f:
                f.write(content)
            logger.debug(f"download_opensubtitle: saved {dst}")
            return [dst]
        logger.debug(f"download_opensubtitle: file already exists {dst}")
        return []
    except Exception as e:
        logger.warning(f"download_opensubtitle failed for tag={tag!r}: {e}")
        return []


# ── Common ──

async def search_all(query: str, language: str = "English", imdb_id: str = "") -> list:
    """Search multiple subtitle sources. Results from sub-plus first, then OpenSubtitles."""
    logger.debug(f"search_all entry: query={query!r}, language={language!r}, imdb_id={imdb_id!r}")
    results = []
    try:
        results = await search_subtitles(query, language)
        logger.debug(f"search_all: sub-plus returned {len(results)} results")
    except Exception as e:
        logger.warning(f"search_all: sub-plus exception: {e}")
    try:
        os_results = await search_subtitles_opensubs(query, imdb_id)
        logger.debug(f"search_all: OpenSubtitles returned {len(os_results)} results")
        results.extend(os_results)
    except Exception as e:
        logger.warning(f"search_all: OpenSubtitles exception: {e}")
    logger.debug(f"search_all: merged {len(results)} total results")
    return results


async def download_subtitle(tag: str, dest_dir: str) -> list[str]:
    """Download subtitle from any source based on tag prefix."""
    logger.debug(f"download_subtitle entry: tag={tag!r}, dest_dir={dest_dir!r}")
    if tag.startswith("opensub:"):
        logger.debug(f"download_subtitle: routing to OpenSubtitles download")
        result = await download_opensubtitle(tag, dest_dir)
        if result:
            logger.debug(f"download_subtitle: OpenSubtitles files saved: {result}")
        else:
            logger.warning(f"download_subtitle: OpenSubtitles download returned no files")
        return result
    # Default: sub-plus.ir
    logger.debug(f"download_subtitle: routing to sub-plus download")
    url = await get_download_link(tag)
    if not url:
        logger.warning(f"download_subtitle: no download link from sub-plus for tag={tag!r}")
        return []
    result = await download_and_extract(url, dest_dir)
    if result:
        logger.debug(f"download_subtitle: sub-plus files saved: {result}")
    else:
        logger.warning(f"download_subtitle: sub-plus download returned no files")
    return result


def find_local_subtitles(media_path: str) -> list[dict]:
    logger.debug(f"find_local_subtitles entry: media_path={media_path!r}")
    dirname = os.path.dirname(media_path)
    basename = os.path.splitext(os.path.basename(media_path))[0]
    found = []
    try:
        for i, fname in enumerate(os.listdir(dirname)):
            name, ext = os.path.splitext(fname)
            if ext.lower() in SUBTITLE_EXTS and name == basename:
                found.append({
                    "type": "local",
                    "index": i,
                    "label": fname,
                    "file": os.path.join(dirname, fname),
                    "codec": ext[1:].lower(),
                    "language": "und",
                    "title": fname,
                })
        logger.debug(f"find_local_subtitles: found {len(found)} local subtitle(s)")
        return found
    except Exception as e:
        logger.warning(f"find_local_subtitles failed for {media_path!r}: {e}")
        return []
