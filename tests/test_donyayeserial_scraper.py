"""Tests for DonyayeSerialScraper."""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.services.scraper import DonyayeSerialScraper


SAMPLE_ARCHIVE_HTML = """
<html>
<body>
<h3>1. Test Movie (2024)</h3>
<p>IMDb Code: <b>tt1234567</b></p>
<p>Title Type: <b>movie</b></p>
<p>IMDb Rates: <b>7.5</b></p>
<p style="color:red"><b>SoftSub</b></p>
<a href="http://dl.example.com/movie.mkv">1080p</a> / 2.5 GB
<hr>
<h3>2. Test Series (2023)</h3>
<p>IMDb Code: <b>tt7654321</b></p>
<p>Title Type: <b>series</b></p>
<p>IMDb Rates: <b>8.0</b></p>
<p style="color:red"><b>SoftSub</b></p>
<p>season 1</p>
<a href="http://dl.example.com/ep1.mkv">Episode 1</a> / 500 MB
</body>
</html>
"""


@pytest.mark.asyncio
async def test_scraper_name():
    scraper = DonyayeSerialScraper()
    assert scraper.name == "donyayeserial"
    assert "DonyayeSerial" in scraper.base_url


@pytest.mark.asyncio
async def test_search_returns_results():
    scraper = DonyayeSerialScraper()

    with patch("app.services.scraper.fetch_archive", new=AsyncMock(return_value=SAMPLE_ARCHIVE_HTML)):
        results = await scraper.search("test")
        assert len(results) >= 1
        # At minimum, "Test Movie" matches "test"
        titles = [r.title for r in results]
        assert any("Test" in t for t in titles)


@pytest.mark.asyncio
async def test_search_no_match():
    scraper = DonyayeSerialScraper()

    with patch("app.services.scraper.fetch_archive", new=AsyncMock(return_value=SAMPLE_ARCHIVE_HTML)):
        results = await scraper.search("xyznonexistent")
        assert results == []


@pytest.mark.asyncio
async def test_search_empty_archive():
    scraper = DonyayeSerialScraper()

    with patch("app.services.scraper.fetch_archive", new=AsyncMock(return_value=None)):
        results = await scraper.search("test")
        assert results == []


@pytest.mark.asyncio
async def test_search_returns_empty_for_page_gt_1():
    scraper = DonyayeSerialScraper()
    results = await scraper.search("test", page=2)
    assert results == []


@pytest.mark.asyncio
async def test_get_download_links_returns_empty():
    scraper = DonyayeSerialScraper()
    links = await scraper.get_download_links("http://example.com")
    assert links.any() is False


@pytest.mark.asyncio
async def test_close_session():
    scraper = DonyayeSerialScraper()
    mock_http = AsyncMock()
    scraper.session = mock_http
    await scraper.close()
    mock_http.aclose.assert_called_once()
    assert scraper.session is None
