import re
import os
import json
import time
import logging
from typing import Optional, List, Dict, Any, Union
from urllib.parse import urljoin
import asyncio

import httpx
from bs4 import BeautifulSoup

from app.services.base_scraper import BaseScraper, SearchResult, DownloadLinks

logger = logging.getLogger(__name__)

BASE_URL = os.environ.get("AZFILM_BASE_URL", "https://azfilm.theazizi.ir")
SEARCH_URL = f"{BASE_URL}/index.php"
REQUEST_TIMEOUT = 10
MAX_RETRIES = 2
BACKOFF_SEC = 1
CACHE_TTL = 3600


class AzfilmScraper(BaseScraper):
    def __init__(self):
        self._base_url = BASE_URL
        self.session = None

    @property
    def name(self) -> str:
        return "azfilm"

    @property
    def base_url(self) -> str:
        return self._base_url

    async def _get_session(self) -> httpx.AsyncClient:
        if self.session is None:
            self.session = httpx.AsyncClient(
                timeout=REQUEST_TIMEOUT,
                follow_redirects=True,
                headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.5',
                }
            )
        return self.session

    async def close(self):
        if self.session:
            await self.session.aclose()
            self.session = None

    async def _fetch_with_retry(self, url: str, params: Optional[dict] = None) -> Optional[str]:
        session = await self._get_session()
        for attempt in range(1, MAX_RETRIES + 2):
            try:
                resp = await session.get(url, params=params)
                resp.raise_for_status()
                return resp.text
            except (httpx.TimeoutException, httpx.ConnectError, httpx.HTTPStatusError) as e:
                logger.warning(f"AzFilm fetch attempt {attempt}/{MAX_RETRIES+1} failed: {e}")
                if attempt <= MAX_RETRIES:
                    await asyncio.sleep(BACKOFF_SEC * attempt)
                else:
                    logger.error(f"AzFilm fetch exhausted retries for {url}")
                    return None

    async def search(self, query: str, page: int = 1) -> List[SearchResult]:
        results = []
        params = {'s': query}
        if page > 1:
            params['page'] = page

        html = await self._fetch_with_retry(SEARCH_URL, params=params)
        if html is None:
            return []

        try:
            soup = BeautifulSoup(html, 'html.parser')
            cards = soup.find_all('a', class_='card')
            for card in cards:
                href = card.get('href', '')
                imdb_match = re.search(r'imdb=tt(\d+)', href)
                if not imdb_match:
                    continue
                imdb_id = f"tt{imdb_match.group(1)}"
                title_elem = card.find('h2', class_='ctitle')
                title = title_elem.get_text(strip=True) if title_elem else ''
                year_elem = card.find('span', class_='cyear')
                year = year_elem.get_text(strip=True) if year_elem else ''
                type_elem = card.find('span', class_='ctype')
                media_type = 'movie'
                if type_elem:
                    type_text = type_elem.get_text(strip=True)
                    if 'سریال' in type_text:
                        media_type = 'tv_series'
                rating_elem = card.find('span', class_='rnum')
                rating = rating_elem.get_text(strip=True) if rating_elem else ''
                subs = []
                sub_elems = card.find_all('span', class_='sbadge')
                for sub in sub_elems:
                    sub_text = sub.get_text(strip=True)
                    if 'زیرنویس' in sub_text:
                        subs.append('SoftSub')
                    elif 'دوبله' in sub_text:
                        subs.append('Dubbed')
                    elif 'بدون زیرنویس' in sub_text:
                        subs.append('NoSub')
                cover_url = ""
                img = card.find("img")
                if img:
                    src = img.get("src", "") or img.get("data-src", "")
                    if src:
                        cover_url = urljoin(self.base_url, src)
                results.append(SearchResult(
                    imdb_id=imdb_id, title=title, year=year,
                    media_type=media_type, imdb_rating=rating,
                    subtitle_types=subs, url=urljoin(self.base_url, href),
                    cover_url=cover_url, source=self.name,
                ))
            logger.info(f"AzFilm: found {len(results)} results for '{query}'")
            return results
        except Exception as e:
            logger.error(f"AzFilm search error for '{query}': {e}")
            return []

    async def get_download_links(self, movie_url: str) -> DownloadLinks:
        links = DownloadLinks()
        html = await self._fetch_with_retry(movie_url)
        if html is None:
            return links

        try:
            soup = BeautifulSoup(html, 'html.parser')
            cover_img = soup.find("img", class_=re.compile(r"(poster|cover|thumbnail|movie-cover)", re.I))
            if not cover_img:
                cover_img = soup.find("div", class_=re.compile(r"(poster|cover)", re.I))
                if cover_img:
                    cover_img = cover_img.find("img")
            if not cover_img:
                cover_img = soup.find("img", src=re.compile(r"(poster|cover|movie)", re.I))
            if cover_img:
                src = cover_img.get("src", "") or cover_img.get("data-src", "")
                if src:
                    links.cover_url = urljoin(self.base_url, src)

            download_containers = soup.find_all(['div', 'table', 'ul'],
                                                class_=re.compile(r'(download|link|quality)', re.I))
            for container in download_containers:
                found = self._extract_links_from_container(container, str(container))
                for link in found:
                    container_text = container.get_text().lower()
                    if 'softsub' in container_text or 'زیرنویس' in container_text:
                        links.softsub.append(link)
                    elif 'dubbed' in container_text or 'دوبله' in container_text:
                        links.dubbed.append(link)
                    elif 'nosub' in container_text or 'بدون' in container_text:
                        links.nosub.append(link)

            tables = soup.find_all('table')
            for table in tables:
                rows = table.find_all('tr')
                for row in rows:
                    cells = row.find_all('td')
                    if len(cells) >= 2:
                        link_elem = cells[0].find('a')
                        if link_elem and link_elem.get('href'):
                            href = link_elem.get('href')
                            if href.endswith(('.mkv', '.mp4', '.torrent')):
                                size = cells[1].get_text(strip=True) if len(cells) > 1 else ''
                                quality = self._extract_quality_from_text(str(row))
                                link = {
                                    'url': urljoin(self.base_url, href),
                                    'label': link_elem.get_text(strip=True),
                                    'size': size, 'quality': quality
                                }
                                links.softsub.append(link)

            total = len(links.softsub) + len(links.dubbed) + len(links.nosub)
            logger.info(f"AzFilm: found {total} download links from {movie_url}")
            return links
        except Exception as e:
            logger.error(f"Error fetching download links from {movie_url}: {e}")
            return links

    def _extract_links_from_container(self, container, html: str) -> List[Dict]:
        links = []
        for a in container.find_all('a', href=True):
            href = a.get('href', '').strip()
            if not href:
                continue
            if not any(href.endswith(ext) for ext in ['.mkv', '.mp4', '.torrent', '.avi', '.m4v']):
                continue
            label = a.get_text(strip=True)
            size = ''
            parent = a.parent
            if parent:
                parent_text = parent.get_text()
                size_match = re.search(r'(\d+(?:\.\d+)?\s*(?:GB|MB|KB))', parent_text, re.I)
                if size_match:
                    size = size_match.group(1)
            quality = self._extract_quality_from_text(label + ' ' + str(container))
            links.append({
                'url': urljoin(self.base_url, href),
                'label': label or os.path.basename(href),
                'size': size, 'quality': quality
            })
        return links

    def _extract_quality_from_text(self, text: str) -> str:
        patterns = [
            (r'(1080p|1080)', '1080p'), (r'(720p|720)', '720p'),
            (r'(480p|480)', '480p'), (r'(4k|2160p)', '4K'),
            (r'(BluRay|Blu-ray)', 'BluRay'), (r'(WEB-DL|WEBDL)', 'WEB-DL'),
        ]
        text_lower = text.lower()
        for pattern, quality in patterns:
            if re.search(pattern, text_lower, re.I):
                return quality
        return 'Unknown'


# Module-level cache for search results (max 200 entries, TTL enforced on get)
_search_cache: Dict[str, tuple] = {}
_SEARCH_CACHE_MAX = 200


def _evict_oldest(cache: Dict, max_size: int):
    from app.services.cache import evict_oldest
    evict_oldest(cache, max_size)


async def search_azfilm(query: str) -> List[Dict]:
    now = time.time()
    cached = _search_cache.get(query)
    if cached and (now - cached[0]) < CACHE_TTL:
        logger.info(f"AzFilm search cache hit for '{query}'")
        return cached[1]

    scraper = AzfilmScraper()
    try:
        results = await scraper.search(query)
        result_dicts = [{
            'imdb_id': r.imdb_id, 'title': r.title, 'year': r.year,
            'media_type': r.media_type, 'imdb_rating': r.imdb_rating,
            'subtitle_types': r.subtitle_types, 'url': r.url,
            'cover_url': r.cover_url,
        } for r in results]
        _search_cache[query] = (time.time(), result_dicts)
        _evict_oldest(_search_cache, _SEARCH_CACHE_MAX)
        return result_dicts
    finally:
        await scraper.close()


# Module-level cache for download links (max 200 entries, TTL enforced on get)
_links_cache: Dict[str, tuple] = {}
_LINKS_CACHE_MAX = 200


async def get_azfilm_downloads(imdb_id: str) -> dict:
    now = time.time()
    cached = _links_cache.get(imdb_id)
    if cached and (now - cached[0]) < CACHE_TTL:
        logger.info(f"AzFilm links cache hit for '{imdb_id}'")
        return cached[1]

    scraper = AzfilmScraper()
    try:
        url = f"{BASE_URL}/movie.php?imdb={imdb_id}"
        links = await scraper.get_download_links(url)
        result = {
            'SoftSub': links.softsub, 'Dubbed': links.dubbed,
            'NoSub': links.nosub, 'cover_url': links.cover_url,
        }
        _links_cache[imdb_id] = (time.time(), result)
        _evict_oldest(_links_cache, _LINKS_CACHE_MAX)
        return result
    finally:
        await scraper.close()


async def get_azfilm_details(imdb_id: str) -> Optional[Dict]:
    links = await get_azfilm_downloads(imdb_id)
    if not any(links.get(k) for k in ("SoftSub", "Dubbed", "NoSub")):
        return None
    return links



