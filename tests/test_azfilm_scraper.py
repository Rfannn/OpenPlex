"""Tests for AzfilmScraper with mocked HTTP."""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.services.azfilm_scraper import AzfilmScraper, search_azfilm, get_azfilm_downloads


SAMPLE_SEARCH_HTML = """
<html>
<body>
<a class="card" href="movie.php?imdb=tt1375666">
  <h2 class="ctitle">Inception</h2>
  <span class="cyear">2010</span>
  <span class="ctype">فیلم</span>
  <span class="rnum">8.8</span>
  <span class="sbadge">زیرنویس</span>
  <span class="sbadge">دوبله</span>
  <img src="img/tt1375666.jpg">
</a>
<a class="card" href="movie.php?imdb=tt0816692">
  <h2 class="ctitle">Interstellar</h2>
  <span class="cyear">2014</span>
  <span class="ctype">سریال</span>
  <span class="rnum">8.7</span>
  <span class="sbadge">زیرنویس</span>
  <img src="img/tt0816692.jpg">
</a>
</body>
</html>
"""

SAMPLE_DETAIL_HTML = """
<html>
<body>
<img class="poster" src="img/tt1375666.jpg">
<table class="download-table">
<tr><td><a href="movie.mkv">1080p</a></td><td>2.5 GB</td></tr>
<tr><td><a href="movie_720.mkv">720p</a></td><td>1.2 GB</td></tr>
</table>
</body>
</html>
"""


@pytest.fixture
def mock_session():
    session = AsyncMock()
    session.get = AsyncMock()
    return session


@pytest.mark.asyncio
async def test_scraper_name():
    scraper = AzfilmScraper()
    assert scraper.name == "azfilm"
    assert "theazizi" in scraper.base_url


@pytest.mark.asyncio
async def test_search_parses_results():
    scraper = AzfilmScraper()
    mock_resp = AsyncMock()
    mock_resp.text = SAMPLE_SEARCH_HTML
    mock_resp.raise_for_status = MagicMock()

    with patch.object(scraper, "_get_session") as mock_get_session:
        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=mock_resp)
        mock_get_session.return_value = mock_session

        results = await scraper.search("inception")
        assert len(results) == 2

        r1 = results[0]
        assert r1.imdb_id == "tt1375666"
        assert r1.title == "Inception"
        assert r1.year == "2010"
        assert r1.media_type == "movie"
        assert r1.imdb_rating == "8.8"
        assert "SoftSub" in r1.subtitle_types
        assert "Dubbed" in r1.subtitle_types
        assert r1.cover_url != ""
        assert r1.source == "azfilm"

        r2 = results[1]
        assert r2.imdb_id == "tt0816692"
        assert r2.title == "Interstellar"
        assert r2.year == "2014"
        assert r2.media_type == "tv_series"  # سریال
        assert "SoftSub" in r2.subtitle_types


@pytest.mark.asyncio
async def test_search_empty_when_no_cards():
    scraper = AzfilmScraper()
    mock_resp = AsyncMock()
    mock_resp.text = "<html><body>No results</body></html>"
    mock_resp.raise_for_status = MagicMock()

    with patch.object(scraper, "_get_session") as mock_get_session:
        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=mock_resp)
        mock_get_session.return_value = mock_session

        results = await scraper.search("nonexistent")
        assert results == []


@pytest.mark.asyncio
async def test_search_handles_http_error():
    scraper = AzfilmScraper()

    with patch.object(scraper, "_get_session") as mock_get_session:
        mock_session = AsyncMock()
        mock_session.get = AsyncMock(side_effect=Exception("Network error"))
        mock_get_session.return_value = mock_session

        results = await scraper.search("error")
        assert results == []


@pytest.mark.asyncio
async def test_get_download_links_parses():
    scraper = AzfilmScraper()
    mock_resp = AsyncMock()
    mock_resp.text = SAMPLE_DETAIL_HTML
    mock_resp.raise_for_status = MagicMock()

    with patch.object(scraper, "_get_session") as mock_get_session:
        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=mock_resp)
        mock_get_session.return_value = mock_session

        links = await scraper.get_download_links("https://azfilm.theazizi.ir/movie.php?imdb=tt1375666")
        assert links.cover_url != ""


@pytest.mark.asyncio
async def test_get_download_links_empty_on_error():
    scraper = AzfilmScraper()
    with patch.object(scraper, "_get_session") as mock_get_session:
        mock_session = AsyncMock()
        mock_session.get = AsyncMock(side_effect=Exception("Network error"))
        mock_get_session.return_value = mock_session

        links = await scraper.get_download_links("http://bad.url")
        assert links.any() is False
        assert links.cover_url == ""


@pytest.mark.asyncio
async def test_convenience_search_azfilm():
    with patch("app.services.azfilm_scraper.AzfilmScraper.search") as mock_search:
        mock_search.return_value = []
        results = await search_azfilm("test")
        assert results == []


@pytest.mark.asyncio
async def test_convenience_get_azfilm_downloads():
    with patch("app.services.azfilm_scraper.AzfilmScraper.get_download_links") as mock_get:
        from app.services.base_scraper import DownloadLinks
        mock_get.return_value = DownloadLinks()
        result = await get_azfilm_downloads("tt1375666")
        assert "SoftSub" in result
        assert result["SoftSub"] == []


@pytest.mark.asyncio
async def test_extract_quality():
    scraper = AzfilmScraper()
    assert scraper._extract_quality_from_text("1080p BluRay") == "1080p"
    assert scraper._extract_quality_from_text("720p WEB-DL") == "720p"
    assert scraper._extract_quality_from_text("4K HDR") == "4K"
    assert scraper._extract_quality_from_text("some random text") == "Unknown"


@pytest.mark.asyncio
async def test_close_session():
    scraper = AzfilmScraper()
    mock_http = AsyncMock()
    scraper.session = mock_http
    await scraper.close()
    mock_http.aclose.assert_called_once()
    assert scraper.session is None
