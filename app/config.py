"""Application configuration — powered by pydantic-settings.

All settings can be set via environment variables or a .env file.
OS env vars take precedence over .env values (useful for Docker).
"""
import os
import platform
import shutil
from pathlib import Path
from typing import Optional, Tuple, List

from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """OpenPlex server configuration.

    Every field maps to an env var (case-insensitive). Example:
        MEDIA_ROOT=/mnt/hdd/media  →  settings.media_root
    """

    # ── Server ────────────────────────────────────────────────────────────────
    env: str = "development"
    host: str = "0.0.0.0"
    port: int = 8185
    debug: bool = False
    secret_key: str = "CHANGE-ME-IN-PRODUCTION"

    # ── Storage ───────────────────────────────────────────────────────────────
    media_root: str = ""
    database_url: str = "sqlite+aiosqlite:///./data/media_gallery.db?timeout=30"
    thumbnail_cache_dir: str = "./thumbnails"
    min_disk_free_bytes: int = 500_000_000

    # ── Downloads (aria2) ─────────────────────────────────────────────────────
    aria2_rpc_port: int = 6801

    # ── Catalog ───────────────────────────────────────────────────────────────
    catalog_auto_refresh: bool = False
    catalog_refresh_interval_hours: int = 24

    # ── CORS ──────────────────────────────────────────────────────────────────
    cors_origins: List[str] = ["*"]

    # ── AI Categorization (MajidAPI) ──────────────────────────────────────────
    majidapi_token: str = ""
    majidapi_gpt35_url: str = "https://api.majidapi.ir/gpt/35"
    majidapi_gpt4_url: str = "https://api.majidapi.ir/gpt/4"

    # ── Metadata APIs ─────────────────────────────────────────────────────────
    tmdb_api_key: str = ""
    tmdb_base_url: str = "https://api.themoviedb.org/3"
    tmdb_image_base: str = "https://image.tmdb.org/t/p/"
    omdb_api_key: str = ""
    fanart_api_key: str = ""
    tvdb_api_key: str = ""

    # ── Subtitles ─────────────────────────────────────────────────────────────
    opensubtitles_username: str = ""
    opensubtitles_password: str = ""
    opensubtitles_api_key: str = ""

    # ── AI Chat (Agnes AI — primary) ──────────────────────────────────────────
    agnes_api_key: str = ""
    agnes_model: str = "agnes-2.0-flash"
    agnes_base_url: str = "https://apihub.agnes-ai.com/v1/chat/completions"

    # ── Local AI (llama-server — fallback, on-demand) ─────────────────────────
    local_ai_url: str = "http://127.0.0.1:8081"
    local_ai_model: str = "qwen2.5-3b"
    local_ai_auto_start: bool = False  # auto-start llama-server when needed

    # ── Deprecated (kept for backwards compat) ────────────────────────────────
    deepseek_proxy_url: str = ""

    # ── Computed / non-env fields ─────────────────────────────────────────────
    thumbnail_size: Tuple[int, int] = (150, 150)
    cache_duration: int = 3600

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
        "case_sensitive": False,
    }

    @property
    def allowed_images(self) -> set:
        return {"png", "jpg", "jpeg", "gif", "bmp", "webp", "svg"}

    @property
    def allowed_videos(self) -> set:
        return {"mp4", "mkv", "webm", "avi", "mov", "ogg", "m4v", "flv", "wmv"}

    @property
    def allowed_audio(self) -> set:
        return {"mp3", "wav", "ogg", "aac", "flac", "m4a"}

    @property
    def allowed_extensions_flat(self) -> set:
        return self.allowed_images | self.allowed_videos | self.allowed_audio

    @property
    def platform(self) -> str:
        return platform.system().lower()

    def check_disk_space(self, path: Optional[str] = None) -> Tuple[bool, int]:
        target = path or self.media_root
        try:
            usage = shutil.disk_usage(target)
            has_space = usage.free >= self.min_disk_free_bytes
            return has_space, usage.free
        except Exception:
            return True, -1


settings = Settings()

# Auto-detect media_root if not set
if not settings.media_root:
    if settings.platform == "windows":
        home = os.environ.get("USERPROFILE", "C:\\")
        settings.media_root = os.path.join(home, "Downloads", "Video")
    else:
        home = os.environ.get("HOME", "/home")
        settings.media_root = os.path.join(home, "Downloads", "Video")

# Ensure directories exist
os.makedirs(settings.thumbnail_cache_dir, exist_ok=True)
os.makedirs("data", exist_ok=True)

import logging
logger = logging.getLogger(__name__)
if logging.getLogger().hasHandlers():
    logger.info("Platform: %s, Media root: %s", settings.platform, settings.media_root)
