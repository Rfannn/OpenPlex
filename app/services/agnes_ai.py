"""Agnes AI client — primary AI service for chat, categorization, and recommendations.

Async HTTP client using httpx with automatic retry on transient failures.
Falls back to local llama-server when Agnes is down or rate-limited.
"""
import json
import logging
import time
from typing import Optional, List, Dict, Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 45.0
MAX_RETRIES = 2
RETRY_DELAY = 1.0  # seconds between retries
_cache: Dict[str, tuple] = {}
_CACHE_MAX = 200
CACHE_TTL = 3600


def is_configured() -> bool:
    return bool(settings.agnes_api_key)


def _evict_oldest():
    from app.services.cache import evict_oldest
    evict_oldest(_cache, _CACHE_MAX)


def _cache_key(messages: list) -> str:
    """Simple cache key from messages."""
    if not messages:
        return ""
    last = messages[-1]
    return f"{last.get('role', '')}:{last.get('content', '')[:200]}"


async def chat(
    messages: List[Dict[str, str]],
    temperature: float = 0.7,
    max_tokens: int = 2048,
    timeout: float = REQUEST_TIMEOUT,
) -> Optional[str]:
    """Send a chat completion request to Agnes AI with automatic retry.

    Returns the assistant response string, or None on failure.
    """
    if not is_configured():
        logger.debug("Agnes AI not configured (no API key)")
        return None

    # Check cache
    ck = _cache_key(messages)
    if ck:
        cached = _cache.get(ck)
        if cached and (time.time() - cached[0]) < CACHE_TTL:
            return cached[1]

    payload = {
        "model": settings.agnes_model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }

    last_error = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                r = await client.post(
                    settings.agnes_base_url,
                    headers={
                        "Authorization": f"Bearer {settings.agnes_api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                if r.status_code == 429:
                    logger.warning("Agnes AI rate limited (429)")
                    return None
                if r.status_code == 401:
                    logger.warning("Agnes AI auth failed (401) — check API key")
                    return None
                r.raise_for_status()
                data = r.json()
                content = data["choices"][0]["message"]["content"].strip()

                # Cache successful response
                if ck:
                    _cache[ck] = (time.time(), content)
                    _evict_oldest()

                return content
        except (httpx.ConnectError, httpx.TimeoutException) as e:
            last_error = e
            if attempt < MAX_RETRIES:
                logger.warning("Agnes AI attempt %d/%d failed: %s — retrying in %.1fs",
                             attempt + 1, MAX_RETRIES + 1, e, RETRY_DELAY)
                await __import__('asyncio').sleep(RETRY_DELAY * (attempt + 1))
            else:
                logger.warning("Agnes AI all retries exhausted: %s", e)
        except Exception as e:
            logger.warning("Agnes AI unexpected error: %s", e)
            return None

    return None


async def chat_stream(
    messages: List[Dict[str, str]],
    temperature: float = 0.7,
    max_tokens: int = 2048,
    timeout: float = 60.0,
):
    """Stream a chat completion from Agnes AI. Yields content chunks."""
    if not is_configured():
        yield json.dumps({"error": "Agnes AI not configured"})
        return

    payload = {
        "model": settings.agnes_model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": True,
    }

    last_error = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                async with client.stream(
                    "POST",
                    settings.agnes_base_url,
                    headers={
                        "Authorization": f"Bearer {settings.agnes_api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                ) as r:
                    if r.status_code == 429:
                        yield json.dumps({"error": "Rate limited"})
                        return
                    if r.status_code == 401:
                        yield json.dumps({"error": "Auth failed — check API key"})
                        return
                    r.raise_for_status()
                    async for line in r.aiter_lines():
                        line = line.strip()
                        if not line or not line.startswith("data: "):
                            continue
                        data_str = line[6:]
                        if data_str == "[DONE]":
                            continue
                        try:
                            data = json.loads(data_str)
                            delta = data.get("choices", [{}])[0].get("delta", {}).get("content", "")
                            if delta:
                                yield delta
                        except json.JSONDecodeError:
                            pass
                    return  # success — exit retry loop
        except (httpx.ConnectError, httpx.TimeoutException) as e:
            last_error = e
            if attempt < MAX_RETRIES:
                logger.warning("Agnes stream attempt %d/%d failed: %s — retrying",
                             attempt + 1, MAX_RETRIES + 1, e)
                await __import__('asyncio').sleep(RETRY_DELAY * (attempt + 1))
            else:
                logger.warning("Agnes stream all retries exhausted: %s", e)
        except Exception as e:
            logger.warning("Agnes stream unexpected error: %s", e)
            yield json.dumps({"error": str(e)})
            return

    # All retries failed — emit error but don't yield it (let caller handle fallback)
    logger.warning("Agnes AI stream unavailable after %d attempts", MAX_RETRIES + 1)


def clear_cache():
    """Clear the Agnes AI response cache."""
    _cache.clear()
