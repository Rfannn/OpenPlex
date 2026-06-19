"""Tests for the scraper registry."""
import pytest
from unittest.mock import patch
from app.services.scraper_registry import (
    get_registry, get_scraper, list_scrapers, search_all, close_all
)
from app.services.base_scraper import BaseScraper, SearchResult


def test_registry_contains_scrapers():
    registry = get_registry()
    assert "azfilm" in registry
    assert "donyayeserial" in registry
    assert len(registry) >= 2


def test_list_scrapers():
    scrapers = list_scrapers()
    assert "azfilm" in scrapers
    assert "donyayeserial" in scrapers


def test_get_scraper():
    scraper = get_scraper("azfilm")
    assert scraper is not None
    assert scraper.name == "azfilm"
    assert isinstance(scraper, BaseScraper)


def test_get_scraper_unknown():
    scraper = get_scraper("nonexistent_scraper")
    assert scraper is None


@pytest.mark.asyncio
async def test_search_all_aggregates():
    """search_all should call search on each registered scraper."""
    with patch("app.services.scraper_registry.get_registry") as mock_get_reg:
        async def empty_search(self, q, page=1): return []
        async def found_search(self, q, page=1): return [SearchResult(imdb_id="tt9999999", title="Found", source="mock2")]
        async def empty_links(self, url): return type("DL", (), {"any": lambda: False, "softsub": [], "dubbed": [], "nosub": [], "cover_url": ""})()
        mock_scraper1 = type("MockScraper1", (BaseScraper,), {
            "name": "mock1",
            "enabled": True,
            "search": empty_search,
            "get_download_links": empty_links,
            "close": lambda self: None,
            "base_url": "",
        })()
        mock_scraper2 = type("MockScraper2", (BaseScraper,), {
            "name": "mock2",
            "enabled": True,
            "search": found_search,
            "get_download_links": empty_links,
            "close": lambda self: None,
            "base_url": "",
        })()
        mock_get_reg.return_value = {"mock1": mock_scraper1, "mock2": mock_scraper2}

        results = await search_all("test")
        assert len(results) == 1
        assert results[0].title == "Found"
        assert results[0].source == "mock2"


@pytest.mark.asyncio
async def test_search_all_handles_failure():
    """If one scraper fails, others should still be queried."""
    with patch("app.services.scraper_registry.get_registry") as mock_get_reg:
        class FailingScraper(BaseScraper):
            @property
            def name(self): return "failing"
            async def search(self, q, page=1): raise Exception("Fail")
            async def get_download_links(self, url): raise Exception("Fail")
            @property
            def base_url(self): return ""
            @property
            def enabled(self): return True

        class WorkingScraper(BaseScraper):
            @property
            def name(self): return "working"
            async def search(self, q, page=1): return [SearchResult(imdb_id="tt0000001", title="OK", source="working")]
            async def get_download_links(self, url): return type("DL", (), {"any": lambda: False, "softsub": [], "dubbed": [], "nosub": [], "cover_url": ""})()
            @property
            def base_url(self): return ""
            @property
            def enabled(self): return True

        mock_get_reg.return_value = {"failing": FailingScraper(), "working": WorkingScraper()}
        results = await search_all("test")
        assert len(results) == 1
        assert results[0].title == "OK"


@pytest.mark.asyncio
async def test_close_all():
    """close_all should not raise."""
    await close_all()
