import subprocess
import json
import logging
import os
import platform
from pathlib import Path

logger = logging.getLogger(__name__)


def find_ffprobe() -> str:
    """Locate ffprobe binary, mirroring the find_ffmpeg() strategy.

    Returns the executable name (or full path) that subprocess can run.
    """
    root = Path(__file__).resolve().parent.parent.parent
    system = platform.system()
    candidates = ["ffprobe"] if system != "Windows" else ["ffprobe.exe", "ffprobe"]
    for c in candidates:
        p = root / c
        if p.exists():
            return str(p.resolve())
    for c in candidates:
        try:
            subprocess.run([c, "-version"], capture_output=True, timeout=3)
            return c
        except Exception:
            continue
    return "ffprobe"


def get_video_metadata(file_path: str) -> dict:
    try:
        ffprobe_path = find_ffprobe()
        cmd = [
            ffprobe_path, "-v", "quiet",
            "-print_format", "json",
            "-show_format", "-show_streams",
            file_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if result.returncode != 0:
            return {}
        data = json.loads(result.stdout)
        info = {}

        # Format info
        if "format" in data:
            fmt = data["format"]
            info["duration"] = float(fmt.get("duration", 0))
            info["size"] = int(fmt.get("size", 0))
            info["bit_rate"] = fmt.get("bit_rate", "")
            info["format"] = fmt.get("format_long_name", fmt.get("format_name", ""))
            info["nb_streams"] = fmt.get("nb_streams", 0)

        # Stream info
        audio_tracks = []
        subtitle_tracks = []
        for stream in data.get("streams", []):
            codec_type = stream.get("codec_type", "")
            if codec_type == "video":
                info["width"] = stream.get("width", 0)
                info["height"] = stream.get("height", 0)
                info["codec"] = stream.get("codec_name", "")
                info["profile"] = stream.get("profile", "")
                info["pixel_format"] = stream.get("pix_fmt", "")
                info["bit_depth"] = stream.get("bits_per_raw_sample", "")
                r_frame_rate = stream.get("r_frame_rate", "0/1")
                if "/" in r_frame_rate:
                    parts = r_frame_rate.split("/")
                    try:
                        num, den = float(parts[0]), float(parts[1])
                        info["fps"] = round(num / den, 3) if den != 0 else 0
                    except (ValueError, IndexError):
                        info["fps"] = 0
                tags = stream.get("tags", {})
                if tags.get("language"):
                    info["video_language"] = tags["language"]
            elif codec_type == "audio":
                audio_tracks.append({
                    "codec": stream.get("codec_name", ""),
                    "sample_rate": int(stream.get("sample_rate", 0)),
                    "channels": stream.get("channels", 0),
                    "channel_layout": stream.get("channel_layout", ""),
                    "bitrate": stream.get("bit_rate", ""),
                    "language": stream.get("tags", {}).get("language", ""),
                    "title": stream.get("tags", {}).get("title", ""),
                })
            elif codec_type == "subtitle":
                subtitle_tracks.append({
                    "codec": stream.get("codec_name", ""),
                    "language": stream.get("tags", {}).get("language", ""),
                    "title": stream.get("tags", {}).get("title", ""),
                })

        if audio_tracks:
            info["audio"] = audio_tracks[0]
            info["audio_tracks"] = audio_tracks
        info["subtitle_count"] = len(subtitle_tracks)
        if subtitle_tracks:
            info["subtitle_tracks"] = subtitle_tracks

        return info
    except Exception as e:
        logger.error(f"Metadata error for {file_path}: {e}")
        return {}


def get_image_metadata(file_path: str) -> dict:
    try:
        from PIL import Image
        with Image.open(file_path) as img:
            info = {
                "width": img.width,
                "height": img.height,
                "format": img.format,
                "mode": img.mode,
            }
            if hasattr(img, "_getexif"):
                exif = img._getexif()
                if exif:
                    tags = {0x0112: "orientation", 0x010F: "make", 0x0110: "model"}
                    for tag_id, name in tags.items():
                        if tag_id in exif:
                            info[name] = exif[tag_id]
            return info
    except Exception as e:
        logger.error(f"Image metadata error: {e}")
        return {}
