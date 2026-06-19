import io
import os
import hashlib
import tempfile
import subprocess
import platform
import logging
import asyncio
from pathlib import Path
from typing import Optional
from concurrent.futures import ThreadPoolExecutor
from PIL import Image

from app.config import settings

logger = logging.getLogger(__name__)
_pool = ThreadPoolExecutor(max_workers=2)


def create_image_thumbnail(image_path: str, size=None) -> Optional[io.BytesIO]:
    if size is None:
        size = settings.thumbnail_size
    try:
        with Image.open(image_path) as img:
            if img.mode in ("RGBA", "LA", "P"):
                rgb_img = Image.new("RGB", img.size, (255, 255, 255))
                if img.mode == "RGBA":
                    rgb_img.paste(img, mask=img.split()[-1])
                else:
                    rgb_img.paste(img)
                img = rgb_img
            img.thumbnail(size, Image.Resampling.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, "JPEG", quality=70, optimize=True)
            buf.seek(0)
            return buf
    except Exception as e:
        logger.error(f"Image thumbnail error: {e}")
        return None


def find_ffmpeg() -> str:
    # Check project root first (bundled)
    root = Path(__file__).resolve().parent.parent.parent
    system = platform.system()
    candidates = ["ffmpeg"] if system != "Windows" else ["ffmpeg.exe", "ffmpeg"]
    for c in candidates:
        p = root / c
        if p.exists():
            return str(p.resolve())
    # Check PATH
    for c in candidates:
        try:
            subprocess.run([c, "-version"], capture_output=True, timeout=3)
            return c
        except Exception:
            continue
    return "ffmpeg"


def _get_duration_seconds(video_path: str) -> Optional[float]:
    """Probe the video and return its duration in seconds."""
    try:
        from app.services.metadata import find_ffprobe
        ffprobe_path = find_ffprobe()
    except Exception:
        ffprobe_path = "ffprobe"
    try:
        cmd = [ffprobe_path,
               "-v", "error", "-show_entries", "format=duration",
               "-of", "default=noprint_wrappers=1:nokey=1", video_path]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if r.returncode == 0 and r.stdout.strip():
            return float(r.stdout.strip())
    except Exception as e:
        logger.warning(f"Could not probe duration for {os.path.basename(video_path)}: {e}")
    return None


def _format_timestamp(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def create_video_thumbnail_ffmpeg(video_path: str, size=None) -> Optional[io.BytesIO]:
    if size is None:
        size = settings.thumbnail_size
    ffmpeg_path = find_ffmpeg()
    tmp = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            tmp = f.name
        duration = _get_duration_seconds(video_path)
        if duration and duration > 0:
            seek_seconds = duration * 0.15
        else:
            seek_seconds = 1.0
        seek_ts = _format_timestamp(seek_seconds)
        cmd = [
            ffmpeg_path, "-i", video_path,
            "-ss", seek_ts,
            "-vframes", "1",
            "-vf", f"scale={size[0]}:{size[1]}:force_original_aspect_ratio=decrease,pad={size[0]}:{size[1]}:(ow-iw)/2:(oh-ih)/2",
            "-q:v", "2", "-y", tmp
        ]
        subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if os.path.exists(tmp) and os.path.getsize(tmp) > 0:
            with open(tmp, "rb") as f:
                data = f.read()
            return io.BytesIO(data)
    except Exception as e:
        logger.error(f"Video thumbnail error: {e}")
    finally:
        if tmp and os.path.exists(tmp):
            try:
                os.unlink(tmp)
            except Exception:
                pass
    return None


def get_video_thumbnail_cached(video_path: str) -> Optional[io.BytesIO]:
    try:
        st = os.stat(video_path)
        key = hashlib.md5(f"{video_path}_{st.st_mtime}".encode()).hexdigest()
        cache_dir = settings.thumbnail_cache_dir
        cache_path = os.path.join(cache_dir, f"video_{key}.jpg")
        if os.path.exists(cache_path) and os.path.getsize(cache_path) > 0:
            with open(cache_path, "rb") as f:
                return io.BytesIO(f.read())
        # Use temp file for atomic write to avoid race conditions
        thumb = create_video_thumbnail_ffmpeg(video_path)
        if thumb:
            tmp_path = cache_path + ".tmp"
            with open(tmp_path, "wb") as f:
                f.write(thumb.getvalue())
            os.replace(tmp_path, cache_path)
            thumb.seek(0)
        return thumb
    except Exception as e:
        logger.error(f"Video thumbnail cache error: {e}")
        return None


async def get_video_thumbnail_async(video_path: str) -> Optional[io.BytesIO]:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_pool, get_video_thumbnail_cached, video_path)


async def create_image_thumbnail_async(image_path: str) -> Optional[io.BytesIO]:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_pool, create_image_thumbnail, image_path)


def create_placeholder_thumbnail(file_type: str) -> io.BytesIO:
    size = settings.thumbnail_size
    img = Image.new("RGB", size, (44, 62, 80))
    from PIL import ImageDraw
    draw = ImageDraw.Draw(img)
    cx, cy = size[0] // 2, size[1] // 2
    if file_type == "video":
        t = 40
        pts = [(cx - t // 2, cy - t // 2), (cx - t // 2, cy + t // 2), (cx + t // 2, cy)]
        draw.polygon(pts, fill=(102, 126, 234))
    else:
        draw.ellipse([cx - 30, cy - 30, cx + 30, cy + 30], fill=(102, 126, 234))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=70)
    buf.seek(0)
    return buf
