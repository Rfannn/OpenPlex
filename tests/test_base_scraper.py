"""Tests for the BaseScraper abstract class and dataclasses."""
import pytest
from app.services.base_scraper import BaseScraper, SearchResult, DownloadLinks


def test_search_result_defaults():
    r = SearchResult()
    assert r.imdb_id == ""
    assert r.title == ""
    assert r.year == ""
    assert r.media_type == "movie"
    assert r.imdb_rating == ""
    assert r.subtitle_types == []
    assert r.url == ""
    assert r.cover_url == ""
    assert r.source == ""


def test_search_result_fields():
    r = SearchResult(
        imdb_id="tt1234567",
        title="Test Movie",
        year="2024",
        media_type="movie",
        imdb_rating="8.5",
        subtitle_types=["SoftSub", "Dubbed"],
        url="https://example.com/movie",
        cover_url="https://example.com/cover.jpg",
        source="azfilm",
    )
    assert r.imdb_id == "tt1234567"
    assert r.title == "Test Movie"
    assert r.year == "2024"
    assert r.media_type == "movie"
    assert r.imdb_rating == "8.5"
    assert r.subtitle_types == ["SoftSub", "Dubbed"]
    assert r.url == "https://example.com/movie"
    assert r.cover_url == "https://example.com/cover.jpg"
    assert r.source == "azfilm"


def test_download_links_defaults():
    dl = DownloadLinks()
    assert dl.softsub == []
    assert dl.dubbed == []
    assert dl.nosub == []
    assert dl.cover_url == ""
    assert dl.any() is False


def test_download_links_any():
    dl = DownloadLinks()
    assert dl.any() is False
    dl.softsub.append({"url": "http://example.com/file.mkv"})
    assert dl.any() is True


def test_download_links_fields():
    dl = DownloadLinks(
        softsub=[{"url": "http://a.com/1.mkv"}],
        dubbed=[{"url": "http://a.com/2.mkv"}],
        nosub=[{"url": "http://a.com/3.mkv"}],
        cover_url="http://a.com/cover.jpg",
    )
    assert len(dl.softsub) == 1
    assert len(dl.dubbed) == 1
    assert len(dl.nosub) == 1
    assert dl.cover_url == "http://a.com/cover.jpg"
    assert dl.any() is True


class ConcreteScraper(BaseScraper):
    @property
    def name(self) -> str:
        return "test_scraper"

    @property
    def base_url(self) -> str:
        return "https://test.example.com"

    async def search(self, query: str, page: int = 1):
        return [
            SearchResult(
                imdb_id="tt9999999",
                title=query,
                year="2024",
                source=self.name,
            )
        ]

    async def get_download_links(self, url_or_id: str):
        return DownloadLinks(
            softsub=[{"url": url_or_id}],
        )


@pytest.mark.asyncio
async def test_concrete_scraper():
    scraper = ConcreteScraper()
    assert scraper.name == "test_scraper"
    assert scraper.base_url == "https://test.example.com"
    assert scraper.enabled is True

    results = await scraper.search("hello")
    assert len(results) == 1
    assert results[0].title == "hello"
    assert results[0].imdb_id == "tt9999999"
    assert results[0].source == "test_scraper"

    links = await scraper.get_download_links("http://dl.example.com/file.mkv")
    assert links.any() is True
    assert links.softsub[0]["url"] == "http://dl.example.com/file.mkv"
    assert links.dubbed == []


@pytest.mark.asyncio
async def test_base_scraper_abstract():
    """Cannot instantiate BaseScraper directly."""
    with pytest.raises(TypeError):
        BaseScraper()
