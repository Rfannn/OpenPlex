"""Settings page — view and edit all server configuration."""
import os
import json
import logging
from pathlib import Path

from fastapi import APIRouter, Request, Depends
from fastapi.responses import JSONResponse

from app.config import settings
from app.dependencies import get_current_user, require_admin
from app.models.user import User

logger = logging.getLogger(__name__)
router = APIRouter(tags=["settings"])

ENV_FILE = Path(".env")


def _read_env() -> dict:
    """Read current .env file into a dict."""
    result = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            result[key.strip()] = value.strip().strip('"').strip("'")
    return result


def _write_env(data: dict):
    """Write settings back to .env file."""
    env = _read_env()
    env.update(data)
    lines = []
    for key, value in env.items():
        if value:
            lines.append(f'{key}="{value}"')
        else:
            lines.append(f"{key}=")
    ENV_FILE.write_text("\n".join(lines) + "\n")


@router.get("/settings")
async def settings_page(request: Request):
    from pathlib import Path
    from fastapi.templating import Jinja2Templates
    tdir = Path(__file__).resolve().parent.parent.parent / "templates"
    templates = Jinja2Templates(directory=str(tdir))
    return templates.TemplateResponse(request, "settings.html")


@router.get("/api/settings")
async def get_settings(user: User = Depends(require_admin)):
    """Return all current settings (redacted secrets)."""
    env = _read_env()
    return {
        "success": True,
        "settings": {
            "server": {
                "host": env.get("HOST", settings.host),
                "port": env.get("PORT", str(settings.port)),
                "debug": env.get("DEBUG", "false"),
                "secret_key": "***" if env.get("SECRET_KEY") else "",
                "media_root": env.get("MEDIA_ROOT", settings.media_root),
            },
            "ai": {
                "agnes_api_key": env.get("AGNES_API_KEY", ""),
                "agnes_model": env.get("AGNES_MODEL", "agnes-2.0-flash"),
                "agnes_base_url": "https://apihub.agnes-ai.com/v1/chat/completions",
                "local_ai_url": env.get("LOCAL_AI_URL", "http://127.0.0.1:8081"),
                "local_ai_model": env.get("LOCAL_AI_MODEL", "qwen2.5-3b"),
                "local_ai_auto_start": env.get("LOCAL_AI_AUTO_START", "false"),
                "majidapi_token": env.get("MAJIDAPI_TOKEN", ""),
            },
            "metadata": {
                "tmdb_api_key": env.get("TMDB_API_KEY", ""),
                "omdb_api_key": env.get("OMDB_API_KEY", ""),
                "fanart_api_key": env.get("FANART_API_KEY", ""),
                "tvdb_api_key": env.get("TVDB_API_KEY", ""),
            },
            "subtitles": {
                "opensubtitles_username": env.get("OPENSUBTITLES_USERNAME", ""),
                "opensubtitles_password": "***" if env.get("OPENSUBTITLES_PASSWORD") else "",
                "opensubtitles_api_key": env.get("OPENSUBTITLES_API_KEY", ""),
            },
            "catalog": {
                "auto_refresh": env.get("CATALOG_AUTO_REFRESH", "false"),
                "refresh_interval_hours": env.get("CATALOG_REFRESH_INTERVAL_HOURS", "24"),
            },
            "downloads": {
                "aria2_rpc_port": env.get("ARIA2_RPC_PORT", "6801"),
            },
            "display": {
                "cors_origins": env.get("CORS_ORIGINS", "*"),
                "thumbnail_cache_dir": env.get("THUMBNAIL_CACHE_DIR", "./thumbnails"),
                "min_disk_free_bytes": env.get("MIN_DISK_FREE_BYTES", "500000000"),
            },
        },
    }


@router.post("/api/settings")
async def update_settings(payload: dict, user: User = Depends(require_admin)):
    """Update settings — writes to .env file."""
    try:
        flat = {}
        for section, values in payload.items():
            if isinstance(values, dict):
                for key, value in values.items():
                    flat[key] = str(value) if value is not None else ""
            else:
                flat[section] = str(values)

        # Don't overwrite secret_key with empty
        if not flat.get("SECRET_KEY"):
            flat.pop("SECRET_KEY", None)

        _write_env(flat)
        logger.info("Settings updated by %s: %s", user.username, list(flat.keys()))
        return {"success": True, "message": "Settings saved. Restart server to apply."}
    except Exception as e:
        logger.error("Failed to update settings: %s", e)
        return {"success": False, "error": str(e)}
