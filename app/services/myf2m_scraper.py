import re
import os
import json
import sqlite3
import logging
from typing import Optional, List
from pathlib import Path
import asyncio

import httpx
from bs4 import BeautifulSoup

from app.services.base_scraper import BaseScraper, SearchResult, DownloadLinks

logger = logging.getLogger(__name__)
DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"


class Myf2mScraper(BaseScraper):
    BASE_URL = "https://www.myf2m.org"

    def __init__(self):
        self.session = None

    @property
    def name(self) -> str:
        return "myf2m"

    @property
    def base_url(self) -> str:
        return self.BASE_URL

    async def _get_session(self) -> httpx.AsyncClient:
        if self.session is None:
            self.session = httpx.AsyncClient(
                timeout=15,
                follow_redirects=True,
                headers={
                    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.5',
                }
            )
        return self.session

    async def close(self):
        if self.session:
            await self.session.aclose()
            self.session = None

    async def search(self, query: str, page: int = 1) -> List[SearchResult]:
        results = []
        session = await self._get_session()
        try:
            resp = await session.get(self.BASE_URL, params={"s": query})
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, 'html.parser')
            articles = soup.find_all('article', class_='entry')
            for article in articles:
                link = article.find('a', href=re.compile(r'https://www\.myf2m\.org/\d+/'))
                if not link:
                    link = article.find('a', href=re.compile(r'https://myf2m\.org/\d+/'))
                if not link:
                    continue
                url = link.get('href', '')
                title_elem = article.find('h2', class_='entry-title')
                title = title_elem.get_text(strip=True) if title_elem else ''
                cover_img = article.find('img', class_='wp-post-image')
                cover_url = ''
                if cover_img:
                    src = cover_img.get('data-src', '') or cover_img.get('src', '')
                    if src:
                        cover_url = self._clean_cover_url(src)
                results.append(SearchResult(
                    imdb_id='', title=title, url=url,
                    cover_url=cover_url, source=self.name,
                ))
            return results
        except (httpx.TimeoutException, httpx.ConnectError, httpx.HTTPStatusError) as e:
            logger.warning(f"myf2m search for '{query}' failed: {e}")
            return []

    async def get_download_links(self, url_or_id: str) -> DownloadLinks:
        return DownloadLinks()

    def _clean_cover_url(self, src: str) -> str:
        """Remove size suffixes from intocdn.top URLs to get full-size image."""
        if 'intocdn.top' not in src:
            return src
        clean = src.replace('-scaled', '').replace('-180x280', '').replace('-360x480', '')
        if clean.endswith(('.jpg', '.jpeg', '.png', '.webp')):
            return clean
        return src

    async def _resolve_cover_from_detail(self, url: str) -> Optional[str]:
        """Fetch detail page and extract the full-size cover."""
        session = await self._get_session()
        try:
            resp = await session.get(url)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, 'html.parser')
            for img in soup.find_all('img'):
                src = img.get('src', '') or img.get('data-src', '')
                if 'intocdn.top/wp-content/uploads' not in src:
                    continue
                if any(x in src.lower() for x in ('avatar', 'unknowen', 'kmplayer', 'logo')):
                    continue
                clean = self._clean_cover_url(src)
                if clean.endswith(('.jpg', '.jpeg', '.png', '.webp')):
                    return clean
            return None
        except Exception as e:
            logger.debug(f"myf2m detail page {url} failed: {e}")
            return None

    async def get_cover_for_imdb(self, imdb_id: str, title: str = '') -> Optional[str]:
        """Search myf2m by title, extract cover from best matching result."""
        if not title:
            title = await self._lookup_title_async(imdb_id)
        if not title:
            logger.debug(f"myf2m: no title for {imdb_id}, skipping")
            return None

        # Search by title
        search_title = re.sub(r'\s*\(\d{4}\)', '', title).strip()
        results = await self.search(search_title)
        if not results:
            # Try with just the first 2-3 words
            words = search_title.split()
            if len(words) > 3:
                results = await self.search(' '.join(words[:3]))
        if not results:
            return None

        # Check cover in search result (thumbnail often available)
        for r in results[:3]:
            if r.cover_url:
                return r.cover_url

        # Try detail page for first result
        if results[0].url:
            return await self._resolve_cover_from_detail(results[0].url)

        return None

    def _lookup_title(self, imdb_id: str) -> str:
        """Look up title from local DB (synchronous — called via run_in_executor)."""
        try:
            db_path = DATA_DIR / "media_gallery.db"
            if not db_path.exists():
                return ''
            conn = sqlite3.connect(str(db_path))
            c = conn.cursor()
            c.execute("SELECT title FROM download_catalog WHERE imdb_code = ?", (imdb_id,))
            row = c.fetchone()
            conn.close()
            return row[0] if row else ''
        except Exception as e:
            logger.debug(f"myf2m: DB lookup for {imdb_id} failed: {e}")
            return ''

    async def _lookup_title_async(self, imdb_id: str) -> str:
        """Async wrapper for _lookup_title to avoid blocking the event loop."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._lookup_title, imdb_id)


_imdb_cover_cache: dict = {}


async def get_myf2m_cover(imdb_id: str, title: str = '') -> Optional[str]:
    """High-level function to get cover URL from myf2m for an IMDB ID."""
    if imdb_id in _imdb_cover_cache:
        return _imdb_cover_cache[imdb_id]
    scraper = Myf2mScraper()
    try:
        cover = await scraper.get_cover_for_imdb(imdb_id, title)
        if cover:
            _imdb_cover_cache[imdb_id] = cover
        return cover
    finally:
        await scraper.close()
