"""
Donyaye Serial Archive Scraper — multi-source with fallback
"""

import re
import json
import logging
import time
from typing import Optional, List, Dict, Any
from urllib.parse import urljoin, urlparse
import asyncio

import httpx
from bs4 import BeautifulSoup, Tag

from app.services.base_scraper import BaseScraper, SearchResult, DownloadLinks
from app.config import settings

logger = logging.getLogger(__name__)

# Multiple archive sources — try each in order until one works
ARCHIVE_URLS = [
    "https://dls2.film2cinemaha.top/DonyayeSerial/donyaye_serial_all_archive.html",
    "https://dls6.film2cinemaha.top/DonyayeSerial/10_thous.html",
]
ARCHIVE_BASE = ARCHIVE_URLS[0].rsplit('/', 1)[0] + '/'
TIMEOUT = 15
MAX_RETRIES = 2
CACHE_TTL = 300  # 5 minutes

# Archive cache: avoid re-fetching + re-parsing entries on every search
_archive_cache = {"data": None, "ts": 0.0, "url": ""}


class DonyayeSerialScraper(BaseScraper):
    def __init__(self):
        self.session = None

    @property
    def name(self) -> str:
        return "donyayeserial"

    @property
    def base_url(self) -> str:
        return ARCHIVE_URL

    async def _get_session(self) -> httpx.AsyncClient:
        if self.session is None:
            self.session = httpx.AsyncClient(
                timeout=TIMEOUT,
                follow_redirects=True,
                headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                }
            )
        return self.session

    async def close(self):
        if self.session:
            await self.session.aclose()
            self.session = None

    async def search(self, query: str, page: int = 1) -> List[SearchResult]:
        """Search the DonyayeSerial archive by title substring."""
        if page > 1:
            return []
        html = await fetch_archive()
        if not html:
            return []
        entries = await parse_archive(html)
        ql = query.lower()
        results = []
        for e in entries:
            if ql not in e.get("title", "").lower():
                continue
            results.append(SearchResult(
                imdb_id=e.get("imdb_code", ""),
                title=e.get("title", ""),
                year=e.get("year", ""),
                media_type="tv_series" if e.get("has_seasons") else "movie",
                imdb_rating=e.get("imdb_rating", ""),
                subtitle_types=[],
                url="",
                cover_url="",
                source=self.name,
            ))
        return results

    async def get_download_links(self, url_or_id: str) -> DownloadLinks:
        """Not directly applicable for archive scraper - downloads come from season pages."""
        return DownloadLinks()


async def fetch_page(url: str, retries: int = MAX_RETRIES) -> Optional[str]:
    """Fetch page with retry logic and better error handling"""
    for attempt in range(retries):
        try:
            async with httpx.AsyncClient(
                timeout=TIMEOUT, 
                follow_redirects=True,
                headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                }
            ) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                return resp.text
        except httpx.ConnectError as e:
            logger.error(f"Connection error to {url}: {e}")
            if attempt == retries - 1:
                return None
            await asyncio.sleep(1)
        except httpx.TimeoutException:
            logger.warning(f"Timeout on {url} (attempt {attempt + 1})")
            if attempt == retries - 1:
                return None
            await asyncio.sleep(1)
        except Exception as e:
            logger.error(f"Failed to fetch {url}: {e}")
            if attempt == retries - 1:
                return None
            await asyncio.sleep(1)
    return None


async def fetch_archive() -> Optional[str]:
    """Fetch the main archive page with caching. Tries multiple sources."""
    global _archive_cache
    now = time.time()
    if _archive_cache["data"] and (now - _archive_cache["ts"]) < CACHE_TTL:
        logger.info("Using cached archive (%d entries, age=%.0fs)", len(_archive_cache["data"]), now - _archive_cache["ts"])
        return _archive_cache["data"]

    # Try each archive URL in order
    for url in ARCHIVE_URLS:
        logger.info("Fetching archive from %s", url)
        html = await fetch_page(url)
        if html and len(html) > 1000:  # Sanity check — valid archive pages are large
            _archive_cache["data"] = html
            _archive_cache["ts"] = time.time()
            _archive_cache["url"] = url
            logger.info("Archive fetched successfully from %s (%d bytes)", url, len(html))
            return html
        logger.warning("Archive fetch failed or too small from %s", url)

    logger.error("All archive sources failed")
    return None


def get_archive_cache_info() -> dict:
    """Return cache status for health/debug endpoints."""
    global _archive_cache
    now = time.time()
    age = now - _archive_cache["ts"] if _archive_cache["ts"] else -1
    return {
        "cached": _archive_cache["data"] is not None,
        "age_seconds": int(age) if age >= 0 else -1,
        "ttl_seconds": CACHE_TTL,
        "url": _archive_cache["url"],
    }


async def fetch_season_page(url: str) -> List[dict]:
    """Fetch and parse a season/directory page with better error handling"""
    if not url:
        logger.warning("Empty URL provided to fetch_season_page")
        return []
    
    # Resolve relative URLs against the archive base
    if not url.startswith('http'):
        resolved = urljoin(ARCHIVE_BASE, url)
        logger.info(f"Resolved relative URL {url} -> {resolved}")
        url = resolved
    
    logger.info(f"Fetching season page: {url}")
    html = await fetch_page(url)
    if not html:
        logger.warning(f"Failed to fetch season page: {url}")
        return []
    
    return parse_apache_listing(html)


def parse_apache_listing(html: str) -> List[dict]:
    """Parse Apache directory listing with better validation"""
    files = []
    try:
        soup = BeautifulSoup(html, "html.parser")
        table = soup.find("table")
        if not table:
            logger.warning("No table found in Apache listing")
            return files
        
        for row in table.find_all("tr"):
            cells = row.find_all("td")
            if len(cells) >= 2:  # Need at least name and size
                link = cells[0].find("a")
                if link:
                    href = link.get("href", "").strip()
                    name = link.get_text(strip=True)
                    size = cells[2].get_text(strip=True) if len(cells) > 2 else ""
                    
                    # Skip parent directory links
                    if href and href.startswith(".."):
                        continue
                    if href and href.startswith("?"):
                        continue
                    if name and href:
                        files.append({
                            "name": name,
                            "url": href,
                            "size": size if size else "Unknown"
                        })
        
        logger.info(f"Found {len(files)} items in directory listing")
        return files
    except Exception as e:
        logger.error(f"Error parsing Apache listing: {e}")
        return []


class CatalogEntry:
    """Original CatalogEntry class - kept for compatibility"""
    def __init__(self):
        self.title = ""
        self.year = ""
        self.imdb_code = ""
        self.title_type = "movie"
        self.imdb_rating = ""
        self.imdb_votes = ""
        self.softsub_links: List[dict] = []
        self.dubbed_links: List[dict] = []
        self.nosub_links: List[dict] = []
        self.has_seasons = False
        self.season_info: Dict[str, List[dict]] = {}


def parse_entry_block(block: str, entry_number: int) -> Optional[CatalogEntry]:
    """Parse a single archive entry block"""
    entry = CatalogEntry()

    # Extract title
    title_match = re.search(rf"<h3>\s*{entry_number}\.\s*(.*?)</h3>", block, re.DOTALL)
    if not title_match:
        return None
    full_title = title_match.group(1).strip()

    # Extract year
    entry.title = full_title.strip()
    # Strip literal " start_year" artifact from source data
    if entry.title.endswith(" start_year"):
        entry.title = entry.title[: -len(" start_year")].strip()
    year_match = re.search(r"(\d{4})\s*$", entry.title)
    if year_match:
        entry.year = year_match.group(1)
        entry.title = entry.title[:year_match.start()].strip()
    entry.title = entry.title.strip()

    # Extract IMDb info
    imdb_match = re.search(r"IMDb Code:</b>\s*(tt\d+)", block, re.IGNORECASE)
    if imdb_match:
        entry.imdb_code = imdb_match.group(1)

    type_match = re.search(r"Title Type:</b>\s*(\w+)", block, re.IGNORECASE)
    if type_match:
        entry.title_type = type_match.group(1)

    votes_match = re.search(r"IMDb Votes:</b>\s*([\d,]+)", block, re.IGNORECASE)
    if votes_match:
        entry.imdb_votes = votes_match.group(1)

    rating_match = re.search(r"IMDb Rates:</b>\s*([\d.]+)", block, re.IGNORECASE)
    if rating_match:
        entry.imdb_rating = rating_match.group(1)

    # Parse sections (SoftSub, Dubbed, NoSub)
    sections = re.split(r'(<p style="color:[^"]*"[^>]*><b>(SoftSub|Dubbed|NoSub)</b></p>)', block, re.IGNORECASE)
    current_section = None
    
    for i, part in enumerate(sections):
        if part in ("SoftSub", "Dubbed", "NoSub"):
            current_section = part
            continue
        if not current_section or not part.strip():
            continue

        # Split into season blocks
        season_blocks = re.split(r'(<p[^>]*>season\s+(\d+)[^<]*</p>)', part, flags=re.IGNORECASE)
        section_links = []

        if len(season_blocks) > 1:
            # Has seasons
            before = season_blocks[0]
            if before.strip():
                links = re.findall(r'<a\s+href="([^"]+)"[^>]*>([^<]+)</a>\s*/\s*([^<\n]*)', before)
                for href, label, size in links:
                    if href.strip().endswith(".mkv"):
                        section_links.append({"url": urljoin(ARCHIVE_BASE, href.strip()), "label": label.strip(), "size": size.strip()})

            for j in range(1, len(season_blocks), 3):
                if j + 2 >= len(season_blocks):
                    break
                season_num_raw = season_blocks[j + 1].strip()
                content = season_blocks[j + 2]
                try:
                    season_num = f"S{int(season_num_raw):02d}"
                except ValueError:
                    continue
                
                links = re.findall(r'<a\s+href="([^"]+)"[^>]*>([^<]+)</a>\s*/\s*([^<\n]*)', content)
                for href, label, size in links:
                    href = urljoin(ARCHIVE_BASE, href.strip())
                    label = label.strip()
                    size = size.strip()
                    entry.has_seasons = True
                    if season_num not in entry.season_info:
                        entry.season_info[season_num] = []
                    entry.season_info[season_num].append({"url": href, "label": label, "size": size})
                else:
                    # No seasons - flat links
                    links = re.findall(r'<a\s+href="([^"]+)"[^>]*>([^<]+)</a>\s*/\s*([^<\n]*)', part)
                    for href, label, size in links:
                        href = urljoin(ARCHIVE_BASE, href.strip())
                        label = label.strip()
                        size = size.strip()
                        if href.endswith(".mkv"):
                            section_links.append({"url": href, "label": label, "size": size})
                        else:
                            # Non-mkv files (e.g. subtitles) stored separately
                            if "EXTRAS" not in entry.season_info:
                                entry.season_info["EXTRAS"] = []
                            entry.season_info["EXTRAS"].append({"url": href, "label": label, "size": size})

        if current_section == "SoftSub":
            entry.softsub_links = section_links
        elif current_section == "Dubbed":
            entry.dubbed_links = section_links
        elif current_section == "NoSub":
            entry.nosub_links = section_links
        current_section = None

    return entry


async def parse_archive(html: str) -> List[dict]:
    """Parse the entire archive page"""
    entries = []
    try:
        soup = BeautifulSoup(html, "html.parser")
        h3_tags = soup.find_all("h3")
        
        for tag in h3_tags:
            match = re.match(r"(\d+)\.\s*", tag.get_text(strip=True))
            if not match:
                continue
            entry_num = int(match.group(1))
            
            # Collect entry HTML
            block_parts = []
            current = tag.find_next_sibling()
            while current and current.name != "h3" and not (current.name == "hr" and not block_parts):
                if current.name == "hr":
                    break
                block_parts.append(str(current))
                current = current.find_next_sibling()
            block_html = str(tag) + "".join(block_parts)

            entry = parse_entry_block(block_html, entry_num)
            if entry:
                entries.append({
                    "imdb_code": entry.imdb_code,
                    "title": entry.title,
                    "year": entry.year,
                    "title_type": entry.title_type,
                    "imdb_rating": entry.imdb_rating,
                    "imdb_votes": entry.imdb_votes,
                    "softsub_links": entry.softsub_links,
                    "dubbed_links": entry.dubbed_links,
                    "nosub_links": entry.nosub_links,
                    "has_seasons": entry.has_seasons,
                    "season_info": entry.season_info,
                })
        
        logger.info(f"Parsed {len(entries)} entries from archive")
        return entries
    except Exception as e:
        logger.error(f"Error parsing archive: {e}")
        return []