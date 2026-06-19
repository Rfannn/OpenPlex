import os
import json
import shutil
import mimetypes
import logging
import urllib.parse
import asyncio
import subprocess
from pathlib import Path
from typing import Optional
import aiofiles
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from fastapi.responses import FileResponse, Response, StreamingResponse
from concurrent.futures import ThreadPoolExecutor
from werkzeug.utils import safe_join

from app.config import settings
from app.dependencies import get_current_user
from app.services.thumbnail import create_image_thumbnail, get_video_thumbnail_cached, create_placeholder_thumbnail
from app.services.metadata import get_video_metadata, get_image_metadata
from app.services import subtitle_service

logger = logging.getLogger(__name__)
router = APIRouter(tags=["media"])
_pool = ThreadPoolExecutor(max_workers=4)

mimetypes.add_type("video/mp4", ".mp4")
mimetypes.add_type("video/webm", ".webm")
mimetypes.add_type("video/x-matroska", ".mkv")
mimetypes.add_type("video/quicktime", ".mov")
mimetypes.add_type("video/x-msvideo", ".avi")
mimetypes.add_type("video/ogg", ".ogv")

VIDEO_MIME = {
    "mp4": "video/mp4", "webm": "video/webm", "mkv": "video/x-matroska",
    "mov": "video/quicktime", "avi": "video/x-msvideo", "ogv": "video/ogg",
    "m4v": "video/x-m4v", "flv": "video/x-flv", "wmv": "video/x-ms-wmv",
}

BROWSER_PLAYABLE_VIDEO = {"mp4", "webm", "ogv"}
TEXT_EXTENSIONS = {"txt", "md", "log", "json", "xml", "yaml", "yml", "csv", "ini", "cfg", "conf", "nfo", "srt", "sub", "ass", "py", "js", "ts", "html", "css", "sh", "bat", "ps1", "env", "gitignore", "dockerfile", "yml", "yaml", "toml", "cfg"}


def is_allowed(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in settings.allowed_extensions_flat


def get_file_type(filename: str) -> str:
    parts = filename.rsplit(".", 1)
    ext = parts[1].lower() if len(parts) > 1 else ""
    if ext in settings.allowed_images:
        return "image"
    if ext in settings.allowed_videos:
        return "video"
    if ext in settings.allowed_audio:
        return "audio"
    return "other"


def resolve_path(filename: str) -> Optional[str]:
    decoded = urllib.parse.unquote(filename)
    norm_media = os.path.normpath(settings.media_root)
    norm_path = os.path.normpath(decoded)
    if norm_path.startswith(norm_media + os.sep) and os.path.isfile(norm_path):
        return norm_path
    safe_path = safe_join(settings.media_root, decoded)
    if safe_path and os.path.isfile(safe_path):
        return str(Path(safe_path).resolve())
    alt = os.path.join(settings.media_root, decoded.replace("/", os.sep))
    if os.path.isfile(alt):
        return str(Path(alt).resolve())
    return None


def is_browser_playable(filename: str) -> bool:
    ext = filename.rsplit(".", 1)[-1].lower()
    return ext in BROWSER_PLAYABLE_VIDEO


def is_text_file(filename: str) -> bool:
    ext = filename.rsplit(".", 1)[-1].lower()
    return ext in TEXT_EXTENSIONS


@router.get("/api/media/{filename:path}")
async def serve_media(request: Request, filename: str, transcode: bool = Query(False), t: float = Query(None)):
    logger.debug("Serve media: filename=%s transcode=%s seek=%s", filename, transcode, t)
    safe_path = resolve_path(filename)
    if not safe_path:
        logger.warning("Media not found: %s", filename)
        raise HTTPException(status_code=404)

    ftype = get_file_type(filename)
    ext = filename.rsplit(".", 1)[-1].lower()

    # Text file preview
    if ftype == "other" and is_text_file(filename):
        try:
            async with aiofiles.open(safe_path, "r", encoding="utf-8", errors="replace") as f:
                content = await f.read()
            return Response(content=content, media_type="text/plain; charset=utf-8")
        except Exception:
            raise HTTPException(status_code=404)

    if not is_allowed(filename):
        raise HTTPException(status_code=404)

    mime = VIDEO_MIME.get(ext, mimetypes.guess_type(filename)[0] or "application/octet-stream") if ftype == "video" else (mimetypes.guess_type(filename)[0] or "application/octet-stream")

    # On-the-fly transcoding for non-browser-playable video
    if ftype == "video" and transcode and ext not in BROWSER_PLAYABLE_VIDEO:
        try:
            return await _transcode_video(safe_path, filename, seek_to=t)
        except HTTPException:
            raise
        except Exception:
            logger.warning(f"Transcode failed for {filename}, falling back to direct stream")

    file_size = os.path.getsize(safe_path)
    range_header = request.headers.get("range")

    if range_header:
        range_match = range_header.replace("bytes=", "").split("-")
        start_str = range_match[0]
        end_str = range_match[1] if len(range_match) > 1 and range_match[1] else ""
        start = int(start_str) if start_str.isdigit() else 0
        end = int(end_str) if end_str.isdigit() else file_size - 1
        end = min(end, file_size - 1)
        cl = end - start + 1

        async def iter_file():
            async with aiofiles.open(safe_path, "rb") as f:
                await f.seek(start)
                remaining = cl
                while remaining > 0:
                    chunk_size = min(65536, remaining)
                    chunk = await f.read(chunk_size)
                    if not chunk:
                        break
                    remaining -= len(chunk)
                    yield chunk

        return StreamingResponse(
            iter_file(),
            status_code=206,
            media_type=mime,
            headers={
                "Content-Range": f"bytes {start}-{end}/{file_size}",
                "Content-Length": str(cl),
                "Accept-Ranges": "bytes",
            }
        )

    return FileResponse(safe_path, media_type=mime)


_transcode_cache_dir = None
TRANSCODE_CACHE_MAX_BYTES = 10 * 1024 * 1024 * 1024  # 10GB


def _get_cache_dir():
    global _transcode_cache_dir
    if _transcode_cache_dir is None:
        _transcode_cache_dir = os.path.join(settings.media_root, ".transcode_cache")
        os.makedirs(_transcode_cache_dir, exist_ok=True)
        _cleanup_stale_tmp(_transcode_cache_dir)
    return _transcode_cache_dir


def _cleanup_stale_tmp(cache_dir: str):
    for fname in os.listdir(cache_dir):
        if fname.endswith(".tmp") or fname.endswith(".failed"):
            try:
                os.remove(os.path.join(cache_dir, fname))
            except OSError:
                pass


def _cleanup_cache_if_oversized(cache_dir: str):
    try:
        files = []
        total = 0
        for fname in os.listdir(cache_dir):
            if not fname.endswith(".mp4"):
                continue
            fpath = os.path.join(cache_dir, fname)
            try:
                st = os.stat(fpath)
                total += st.st_size
                files.append((st.st_mtime, fpath, st.st_size))
            except OSError:
                pass
        if total <= TRANSCODE_CACHE_MAX_BYTES:
            return
        files.sort()
        for _, fpath, fsize in files:
            if total <= TRANSCODE_CACHE_MAX_BYTES * 0.8:
                break
            try:
                os.remove(fpath)
                total -= fsize
                logger.info(f"Transcode cache evicted: {os.path.basename(fpath)}")
            except OSError:
                pass
    except Exception as e:
        logger.warning(f"Transcode cache cleanup failed: {e}")


_transcode_locks = {}  # cache_key -> asyncio.Lock
_active_transcodes = {}  # cache_key -> {"process": subprocess.Popen, "tmp_path": str}


async def _abort_transcode(cache_key: str):
    """Kill any running ffmpeg for this cache_key and clean up its temp file."""
    existing = _active_transcodes.pop(cache_key, None)
    if existing:
        proc = existing["process"]
        tmp = existing["tmp_path"]
        if proc and proc.poll() is None:
            try:
                proc.terminate()
                await asyncio.get_event_loop().run_in_executor(None, proc.wait, 3)
            except Exception:
                pass
            if proc.poll() is None:
                try: proc.kill()
                except: pass
        if tmp and os.path.exists(tmp):
            try: os.remove(tmp)
            except OSError: pass


async def _transcode_video(safe_path: str, filename: str, seek_to: float = None):
    """Transcode non-browser-playable video to MP4.

    Phases:
      1. First request: ffmpeg writes to a temp file.  While it runs we
         poll the growing file and stream chunks to the client (so playback
         starts quickly).  When ffmpeg finishes the temp is atomically
         renamed to the final cache path.
      2. Subsequent requests (seeks, replays): serve the cached copy with
         full HTTP range-request support — seeking is instant.
    """
    import hashlib
    import subprocess as sp
    from app.services.thumbnail import find_ffmpeg

    ffmpeg_path = find_ffmpeg()
    if not ffmpeg_path:
        raise HTTPException(status_code=400, detail="ffmpeg not available for transcoding")

    try:
        from app.services.metadata import find_ffprobe
        ffprobe_path = find_ffprobe()
    except Exception:
        ffprobe_path = "ffprobe"

    cache_key = hashlib.md5(safe_path.encode()).hexdigest()
    cache_path = os.path.join(_get_cache_dir(), cache_key + ".mp4")

    # ── Cached → serve immediately (full range support) ──
    if os.path.exists(cache_path):
        return FileResponse(
            cache_path, media_type="video/mp4",
            headers={"Accept-Ranges": "bytes", "Content-Disposition": "inline"}
        )

    # ── Pre-check: validate file with ffprobe before transcoding ──
    try:
        probe_cmd = [ffprobe_path,
                     "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=codec_name",
                     "-of", "default=nokey=1:noprint_wrappers=1", safe_path]
        probe = sp.run(probe_cmd, capture_output=True, text=True, timeout=15)
        if probe.returncode != 0 or not probe.stdout.strip():
            logger.warning(f"ffprobe pre-check failed for {filename}, serving directly")
            import mimetypes
            mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
            return FileResponse(safe_path, media_type=mime)
    except (sp.TimeoutExpired, FileNotFoundError):
        pass  # Skip pre-check if ffprobe not available, proceed with transcode

    # ── Kill any in-progress transcode (seek restart) ──
    # When the client seeks during transcoding, it re-requests with t=time.
    # We must kill the old ffmpeg so it doesn't hold the lock and waste CPU.
    await _abort_transcode(cache_key)

    # ── Lock to prevent double-transcode ──
    if cache_key not in _transcode_locks:
        _transcode_locks[cache_key] = asyncio.Lock()

    fail_marker = cache_path + ".failed"
    # If a previous transcode attempt failed twice (marker exists from a
    # prior session), serve the original file directly. The marker gets
    # created only after the no-audio retry also fails.
    if os.path.exists(fail_marker):
        import mimetypes
        mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        return FileResponse(safe_path, media_type=mime)

    async with _transcode_locks[cache_key]:
        if os.path.exists(cache_path):
            return FileResponse(cache_path, media_type="video/mp4",
                                headers={"Accept-Ranges": "bytes", "Content-Disposition": "inline"})

        tmp_path = cache_path + ".tmp"
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

        # Build ffmpeg command — always re-encode for browser compatibility.
        # Use fragmented MP4 with flush_packets so the output file is
        # readable while ffmpeg is still writing.
        # -map 0:v:0   : take first video stream
        # -map 0:a:0?  : take first audio stream if present (optional, won't fail)
        # -map -0:s    : drop all subtitle streams (avoids codec errors)
        # -c:a aac     : re-encode audio to AAC (handles DTS/TrueHD/AC3/anything)
        # -fflags +genpts : generate PTS if missing
        # -err_detect ignore_err : continue on decode errors
        cmd = [ffmpeg_path, "-hide_banner", "-loglevel", "error"]
        if seek_to and seek_to > 0:
            cmd += ["-ss", str(seek_to)]
        cmd += ["-fflags", "+genpts", "-err_detect", "ignore_err",
                "-i", safe_path,
                "-map", "0:v:0", "-map", "0:a:0?", "-map", "-0:s",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                "-pix_fmt", "yuv420p", "-profile:v", "main",
                "-c:a", "aac", "-b:a", "192k", "-ac", "2",
                "-movflags", "+frag_keyframe+empty_moov",
                "-f", "mp4",
                "-y", tmp_path]

        display_name = os.path.basename(filename.rsplit(".", 1)[0] + ".mp4")
        logger.info(f"Transcoding (growing file): {display_name}")

        # Start ffmpeg in a thread
        loop = asyncio.get_event_loop()

        def start_ffmpeg(c):
            try:
                return sp.Popen(c, stdout=sp.DEVNULL, stderr=sp.PIPE)
            except Exception as e:
                logger.error(f"Failed to start ffmpeg: {e}")
                raise

        try:
            process = await loop.run_in_executor(_pool, start_ffmpeg, cmd)
        except Exception as e:
            logger.error(f"Could not launch ffmpeg for {display_name}: {e}")
            raise HTTPException(status_code=500, detail="Could not start transcoder")

        _active_transcodes[cache_key] = {"process": process, "tmp_path": tmp_path}
        complete = False
        no_audio_fallback_used = False

        async def iter_growing_file():
            """Yield chunks from the growing temp file as they're written."""
            nonlocal complete
            nonlocal process
            nonlocal no_audio_fallback_used
            last_pos = 0
            try:
                while True:
                    try:
                        cur = os.path.getsize(tmp_path)
                    except OSError:
                        cur = 0

                    if cur > last_pos:
                        try:
                            with open(tmp_path, "rb") as f:
                                f.seek(last_pos)
                                to_read = cur - last_pos
                                while to_read > 0:
                                    chunk = f.read(min(65536, to_read))
                                    if not chunk:
                                        break
                                    yield chunk
                                    to_read -= len(chunk)
                                    last_pos += len(chunk)
                        except OSError as e:
                            logger.warning(f"Error reading {tmp_path}: {e}")
                            break

                    # Check whether ffmpeg is still alive
                    rc = process.poll()
                    if rc is not None:
                        # Drain any leftover bytes
                        try:
                            cur = os.path.getsize(tmp_path)
                            if cur > last_pos:
                                with open(tmp_path, "rb") as f:
                                    f.seek(last_pos)
                                    chunk = f.read()
                                    if chunk:
                                        yield chunk
                                        last_pos += len(chunk)
                        except OSError:
                            pass
                        if rc != 0:
                            _stderr = process.stderr.read().decode("utf-8", errors="replace") if process.stderr else ""
                            logger.warning(f"ffmpeg exit {rc} for {display_name}: {_stderr[:2000]}")

                            # If we haven't tried yet and the error suggests audio issue,
                            # retry once with audio dropped.
                            if not no_audio_fallback_used and _stderr:
                                lower_err = _stderr.lower()
                                audio_failure = any(s in lower_err for s in [
                                    "dca", "dts", "truehd", "eac3", "ec-3",
                                    "invalid argument", "decoder not found",
                                    "automatic bitstream filtering",
                                ])
                                if audio_failure or not _stderr.strip():
                                    logger.info(f"Retrying transcode for {display_name} with audio disabled")
                                    no_audio_fallback_used = True
                                    try:
                                        if os.path.exists(tmp_path):
                                            os.remove(tmp_path)
                                    except OSError:
                                        pass
                                    retry_cmd = [ffmpeg_path, "-hide_banner", "-loglevel", "error"]
                                    if seek_to and seek_to > 0:
                                        retry_cmd += ["-ss", str(seek_to)]
                                    retry_cmd += [
                                        "-fflags", "+genpts", "-err_detect", "ignore_err",
                                        "-i", safe_path,
                                        "-map", "0:v:0", "-an",
                                        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                                        "-pix_fmt", "yuv420p", "-profile:v", "main",
                                        "-movflags", "+frag_keyframe+empty_moov",
                                        "-f", "mp4", "-y", tmp_path,
                                    ]
                                    try:
                                        process = await loop.run_in_executor(_pool, start_ffmpeg, retry_cmd)
                                        _active_transcodes[cache_key] = {"process": process, "tmp_path": tmp_path}
                                        last_pos = 0
                                        continue
                                    except Exception as e:
                                        logger.warning(f"ffmpeg retry launch failed: {e}")
                            # Final failure — write fail marker so future
                            # requests serve the original file directly.
                            try:
                                with open(fail_marker, "w") as f:
                                    f.write(str(rc))
                                logger.info(f"Transcode failed marker written for {display_name}")
                            except OSError:
                                pass
                            # Final failure — log and break so the client gets
                            # whatever bytes were written (browser will show an error).
                            break
                        else:
                            complete = True
                        break

                    await asyncio.sleep(0.2)
            except GeneratorExit:
                pass
            finally:
                _active_transcodes.pop(cache_key, None)
                if process and process.returncode is None:
                    try:
                        process.kill()
                    except Exception:
                        pass
                if complete:
                    try:
                        os.replace(tmp_path, cache_path)
                        logger.info(f"Transcode cached: {display_name}")
                        _cleanup_cache_if_oversized(_get_cache_dir())
                    except OSError as e:
                        logger.warning(f"Could not rename temp file: {e}")
                else:
                    try:
                        if os.path.exists(tmp_path):
                            os.remove(tmp_path)
                    except OSError:
                        pass

        response = StreamingResponse(
            iter_growing_file(),
            media_type="video/mp4",
            headers={
                "Content-Disposition": f'inline; filename="{display_name}"',
            }
        )

        # Register cleanup on disconnect — if the generator's finally block
        # didn't run (e.g. event-loop cancellation), this ensures the temp
        # file is still removed.
        async def _cleanup():
            await asyncio.sleep(5)
            if not complete and os.path.exists(tmp_path):
                try: os.remove(tmp_path)
                except: pass
                if process.returncode is None:
                    try: process.kill()
                    except: pass

        asyncio.create_task(_cleanup())
        return response


@router.get("/api/thumbnail/{filename:path}")
async def serve_thumbnail(filename: str):
    logger.debug("Serve thumbnail: filename=%s", filename)
    safe_path = resolve_path(filename)
    if not safe_path:
        logger.warning("Thumbnail not found: %s", filename)
        raise HTTPException(status_code=404)

    ftype = get_file_type(filename)
    thumb = None
    if ftype == "image":
        thumb = await asyncio.get_event_loop().run_in_executor(_pool, create_image_thumbnail, safe_path)
    elif ftype == "video":
        thumb = await asyncio.get_event_loop().run_in_executor(_pool, get_video_thumbnail_cached, safe_path)

    if thumb:
        return Response(content=thumb.getvalue(), media_type="image/jpeg",
                        headers={"Cache-Control": "public, max-age=86400"})

    placeholder = create_placeholder_thumbnail(ftype)
    return Response(content=placeholder.getvalue(), media_type="image/jpeg")


@router.get("/api/download/{filename:path}")
async def download_file(filename: str):
    logger.debug("Download file: filename=%s", filename)
    safe_path = resolve_path(filename)
    if not safe_path:
        logger.warning("Download file not found: %s", filename)
        raise HTTPException(status_code=404)
    return FileResponse(
        safe_path,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{os.path.basename(safe_path)}"'}
    )


@router.get("/api/stream")
async def stream_media(request: Request, path: str = Query(...), transcode: bool = Query(False), t: float = Query(None)):
    """Stream media file — uses query param URL so IDM doesn't intercept it."""
    logger.debug("Stream media: path=%s transcode=%s seek=%s", path, transcode, t)
    safe_path = resolve_path(path)
    if not safe_path:
        logger.warning("Stream media not found: %s", path)
        raise HTTPException(status_code=404)

    ftype = get_file_type(path)
    ext = path.rsplit(".", 1)[-1].lower()

    # On-the-fly transcoding for non-browser-playable video
    if ftype == "video" and transcode and ext not in BROWSER_PLAYABLE_VIDEO:
        try:
            result = await _transcode_video(safe_path, path, seek_to=t)
            return result
        except HTTPException:
            raise
        except Exception:
            logger.warning(f"Transcode failed for {path}, falling back to direct stream")

    mime = VIDEO_MIME.get(ext, mimetypes.guess_type(path)[0] or "application/octet-stream") if ftype == "video" else (mimetypes.guess_type(path)[0] or "application/octet-stream")

    file_size = os.path.getsize(safe_path)
    range_header = request.headers.get("range")

    if range_header:
        range_match = range_header.replace("bytes=", "").split("-")
        start_str = range_match[0]
        end_str = range_match[1] if len(range_match) > 1 and range_match[1] else ""
        start = int(start_str) if start_str.isdigit() else 0
        end = int(end_str) if end_str.isdigit() else file_size - 1
        end = min(end, file_size - 1)
        cl = end - start + 1

        async def iter_file():
            async with aiofiles.open(safe_path, "rb") as f:
                await f.seek(start)
                remaining = cl
                while remaining > 0:
                    chunk_size = min(65536, remaining)
                    chunk = await f.read(chunk_size)
                    if not chunk:
                        break
                    remaining -= len(chunk)
                    yield chunk

        return StreamingResponse(
            iter_file(),
            status_code=206,
            media_type=mime,
            headers={
                "Content-Range": f"bytes {start}-{end}/{file_size}",
                "Content-Length": str(cl),
                "Accept-Ranges": "bytes",
                "Content-Disposition": "inline",
            }
        )

    return FileResponse(
        safe_path,
        media_type=mime,
        headers={
            "Accept-Ranges": "bytes",
            "Content-Disposition": "inline",
        }
    )


@router.get("/api/metadata/{filename:path}")
async def media_metadata(filename: str):
    logger.debug("Media metadata: filename=%s", filename)
    safe_path = resolve_path(filename)
    if not safe_path:
        logger.warning("Metadata - file not found: %s", filename)
        raise HTTPException(status_code=404)
    ftype = get_file_type(filename)
    if ftype == "video":
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(_pool, get_video_metadata, safe_path)
    elif ftype == "image":
        return get_image_metadata(safe_path)
    elif ftype == "other":
        stat = os.stat(safe_path)
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        return {
            "size": stat.st_size,
            "modified": stat.st_mtime,
            "ext": ext,
        }
    return {}


@router.get("/api/transcode/status")
async def transcode_status(path: str = Query(...)):
    """Check whether a transcoded cache file is ready for a given path."""
    logger.debug("Transcode status: path=%s", path)
    safe_path = resolve_path(path)
    if not safe_path:
        logger.warning("Transcode status - path not found: %s", path)
        return {"ready": False}
    import hashlib
    cache_key = hashlib.md5(safe_path.encode()).hexdigest()
    cache_path = os.path.join(_get_cache_dir(), cache_key + ".mp4")
    ready = os.path.exists(cache_path)
    return {"ready": ready, "size": os.path.getsize(cache_path) if ready else 0}


@router.get("/api/subtitles/search")
async def search_subtitles_api(q: str = Query(...), l: str = Query("English")):
    """Search for subtitles across multiple sources (sub-plus.ir + OpenSubtitles)."""
    logger.debug("Search subtitles: q=%s lang=%s", q, l)
    results = await subtitle_service.search_all(q, l)
    logger.debug("Subtitle search results: q=%s count=%d", q, len(results) if results else 0)
    return {"success": True, "results": results}


@router.post("/api/subtitles/download")
async def download_subtitle_api(data: dict):
    """Download subtitle from any source and save next to media file."""
    tag = data.get("tag")
    media_path = data.get("media_path")
    logger.debug("Download subtitle: tag=%s media_path=%s", tag, media_path)
    if not tag or not media_path:
        logger.warning("Download subtitle - missing required fields: tag=%s media_path=%s", tag, media_path)
        raise HTTPException(status_code=400, detail="tag and media_path required")
    safe_path = resolve_path(media_path)
    if not safe_path:
        raise HTTPException(status_code=404, detail="Media file not found")
    dest_dir = os.path.dirname(safe_path)
    saved = await subtitle_service.download_subtitle(tag, dest_dir)
    if not saved:
        return {"success": False, "detail": "Subtitle source returned no files"}
    return {"success": True, "saved": saved}


@router.get("/api/subtitles/{filename:path}")
async def get_subtitle_tracks(filename: str, track: int = Query(None), local: int = Query(0)):
    """Detect subtitle tracks: built-in in containers, or local .srt/.ass files."""
    logger.debug("Get subtitle tracks: filename=%s track=%s local=%s", filename, track, local)
    safe_path = resolve_path(filename)
    if not safe_path:
        logger.warning("Subtitle tracks - file not found: %s", filename)
        raise HTTPException(status_code=404)

    # If track is specified, extract that track
    if track is not None:
        if local:
            local_subs = subtitle_service.find_local_subtitles(safe_path)
            local_track = next((s for s in local_subs if s.get("index") == track), None)
            if local_track:
                try:
                    async with aiofiles.open(local_track["file"], "r", encoding="utf-8", errors="replace") as f:
                        content = await f.read()
                    return Response(content=content, media_type="text/plain; charset=utf-8")
                except Exception:
                    pass
            return Response(status_code=204)
        try:
            ffmpeg_path = shutil.which("ffmpeg")
            if not ffmpeg_path:
                raise HTTPException(status_code=500, detail="ffmpeg not found in PATH")
            result = await asyncio.to_thread(
                lambda: subprocess.run(
                    [ffmpeg_path, "-v", "quiet", "-y", "-i", safe_path,
                     "-map", f"0:{track}", "-f", "srt", "pipe:1"],
                    capture_output=True, timeout=30
                )
            )
            if not result.stdout or not result.stdout.strip():
                logger.warning(f"Subtitle extract empty output for {filename} track {track}: {result.stderr.decode('utf-8','replace')[:500]}")
                return Response(status_code=204)
            return Response(content=result.stdout, media_type="text/plain; charset=utf-8")
        except FileNotFoundError:
            raise HTTPException(status_code=500, detail="ffmpeg not installed")
        except subprocess.TimeoutExpired:
            raise HTTPException(status_code=504, detail="Subtitle extraction timed out")
        except Exception as e:
            logger.warning(f"Subtitle extraction failed for {filename} track {track}: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="Extraction failed")

    # Collect both embedded and local tracks
    tracks = []

    # Local .srt/.ass files
    local_subs = subtitle_service.find_local_subtitles(safe_path)
    for sub in local_subs:
        tracks.append({
            "type": "local",
            "index": len(tracks),
            "codec": sub["codec"],
            "language": sub["language"],
            "title": sub["label"],
            "file": sub["file"],
        })

    # Embedded subtitle tracks (MKV/MP4 etc.)
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext in ("mkv", "mp4", "m4v", "webm", "avi", "mov"):
        try:
            result = await asyncio.to_thread(
                lambda: subprocess.run(
                    ["ffprobe", "-v", "quiet", "-print_format", "json",
                     "-show_streams", "-select_streams", "s", safe_path],
                    capture_output=True, timeout=15
                )
            )
            if result.stdout:
                data = json.loads(result.stdout.decode("utf-8", errors="replace"))
                for s in data.get("streams", []):
                    idx = s.get("index", 0)
                    codec = s.get("codec_name", "")
                    lang = s.get("tags", {}).get("language", "und")
                    title = s.get("tags", {}).get("title", f"Track {idx}")
                    tracks.append({
                        "type": "embedded",
                        "index": idx,
                        "codec": codec,
                        "language": lang,
                        "title": title,
                    })
        except Exception as e:
            logger.warning(f"Subtitle probe failed for {filename}: {e}", exc_info=True)

    return {"success": True, "tracks": tracks}

@router.get("/api/media/transcode/{filename:path}")
async def transcode_video(
    filename: str,
    height: int = Query(720, description="Target height: 360, 480, 720, 1080"),
):
    """Transcode video to target resolution and stream as download."""
    logger.debug("Transcode video: filename=%s height=%d", filename, height)
    safe_path = resolve_path(filename)
    if not safe_path:
        logger.warning("Transcode video - file not found: %s", filename)
        raise HTTPException(status_code=404)

    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ("mkv", "mp4", "m4v", "webm", "avi", "mov"):
        raise HTTPException(status_code=400, detail="Unsupported video format")

    # Probe for original resolution
    try:
        result = await asyncio.to_thread(
            lambda: subprocess.run(
                ["ffprobe", "-v", "quiet", "-print_format", "json",
                 "-select_streams", "v:0", "-show_streams", safe_path],
                capture_output=True, timeout=10
            )
        )
        data = json.loads(result.stdout.decode("utf-8", errors="replace"))
        streams = data.get("streams", [])
        orig_height = int(streams[0].get("height", 0)) if streams else 0
    except Exception:
        orig_height = 0

    target = min(height, orig_height) if orig_height > 0 else height

    crf = {1080: 23, 720: 22, 480: 20, 360: 18}.get(target, 23)

    base = os.path.splitext(os.path.basename(safe_path))[0]
    out_name = f"{base}_{target}p.mp4"

    async def stream_transcode():
        loop = asyncio.get_event_loop()
        proc = await loop.run_in_executor(_pool, lambda: subprocess.Popen(
            ["ffmpeg", "-i", safe_path,
             "-vf", f"scale=-2:{target}",
             "-c:v", "libx264", "-preset", "fast", "-crf", str(crf),
             "-pix_fmt", "yuv420p", "-profile:v", "main",
             "-c:a", "aac", "-b:a", "128k",
             "-movflags", "+frag_keyframe+empty_moov",
             "-f", "mp4", "pipe:1"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        ))
        try:
            while True:
                chunk = await loop.run_in_executor(_pool, proc.stdout.read, 65536)
                if not chunk:
                    break
                yield chunk
            rc = await loop.run_in_executor(_pool, proc.wait)
            if rc != 0:
                err = await loop.run_in_executor(_pool, proc.stderr.read)
                logger.warning(f"ffmpeg transcode exit {rc}: {err.decode('utf-8','replace')[:500]}")
        finally:
            if proc.returncode is None:
                proc.terminate()
                await loop.run_in_executor(_pool, proc.wait)

    return StreamingResponse(
        stream_transcode(),
        media_type="video/mp4",
        headers={"Content-Disposition": f'attachment; filename="{out_name}"'},
    )
