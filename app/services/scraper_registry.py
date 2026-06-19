import logging
import time
from typing import Dict, List, Optional, Type

from app.services.base_scraper import BaseScraper, SearchResult, DownloadLinks
from app.services.scraper import DonyayeSerialScraper
from app.services.azfilm_scraper import AzfilmScraper
from app.services.myf2m_scraper import Myf2mScraper

logger = logging.getLogger(__name__)

_REGISTRY: Dict[str, BaseScraper] = {}
_INITIALIZED = False

# Per-scraper health tracking
_HEALTH: Dict[str, dict] = {}
_HEALTH_FAIL_THRESHOLD = 3
_HEALTH_COOLDOWN = 300  # 5 min auto-disable after threshold


def _get_health(name: str) -> dict:
    if name not in _HEALTH:
        _HEALTH[name] = {
            "consecutive_fails": 0,
            "total_fails": 0,
            "total_searches": 0,
            "last_error": None,
            "last_success_ts": None,
            "last_error_ts": None,
            "healthy": True,
            "cooldown_until": 0,
        }
    return _HEALTH[name]


def _discover_scrapers() -> Dict[str, BaseScraper]:
    scrapers: Dict[str, BaseScraper] = {}
    for cls in [DonyayeSerialScraper, AzfilmScraper, Myf2mScraper]:
        try:
            inst = cls()
            if inst.enabled:
                scrapers[inst.name] = inst
                _get_health(inst.name)  # ensure health entry
                logger.info(f"Registered scraper: {inst.name}")
        except Exception as e:
            logger.warning(f"Failed to register scraper {cls.__name__}: {e}")
    return scrapers


def get_registry() -> Dict[str, BaseScraper]:
    global _REGISTRY, _INITIALIZED
    if not _INITIALIZED:
        _REGISTRY = _discover_scrapers()
        _INITIALIZED = True
    return _REGISTRY


def get_scraper(name: str) -> Optional[BaseScraper]:
    return get_registry().get(name)


def list_scrapers() -> List[str]:
    return list(get_registry().keys())


async def search_all(query: str) -> List[SearchResult]:
    results: List[SearchResult] = []
    now = time.time()
    for name, scraper in get_registry().items():
        health = _get_health(name)
        # Check cooldown
        if health["cooldown_until"] > now:
            logger.info(f"Scraper '{name}' in cooldown ({health['cooldown_until'] - now:.0f}s remaining), skipping")
            continue
        try:
            r = await scraper.search(query)
            for res in r:
                res.source = name
            results.extend(r)
            # Reset consecutive fails on success
            health["consecutive_fails"] = 0
            health["total_searches"] += 1
            health["last_success_ts"] = now
            health["healthy"] = True
        except Exception as e:
            health["total_searches"] += 1
            health["consecutive_fails"] += 1
            health["total_fails"] += 1
            health["last_error"] = str(e)[:200]
            health["last_error_ts"] = now
            if health["consecutive_fails"] >= _HEALTH_FAIL_THRESHOLD:
                health["healthy"] = False
                health["cooldown_until"] = now + _HEALTH_COOLDOWN
                logger.warning(f"Scraper '{name}' auto-disabled for {_HEALTH_COOLDOWN}s after {_HEALTH_FAIL_THRESHOLD} consecutive failures")
            logger.warning(f"Search on '{name}' failed for '{query}': {e}")
    return results


async def close_all():
    for name, scraper in _REGISTRY.items():
        try:
            await scraper.close()
            logger.info(f"Scraper '{name}' closed")
        except Exception as e:
            logger.warning(f"Error closing scraper '{name}': {e}")


def get_health() -> Dict[str, dict]:
    """Return health stats for all scrapers."""
    return {
        name: dict(health) for name, health in _HEALTH.items()
    }


def reset_health(name: str):
    """Manually reset health for a scraper (e.g. after admin intervention)."""
    if name in _HEALTH:
        _HEALTH[name]["consecutive_fails"] = 0
        _HEALTH[name]["healthy"] = True
        _HEALTH[name]["cooldown_until"] = 0
        logger.info(f"Scraper '{name}' health manually reset")
