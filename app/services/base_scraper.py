import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    imdb_id: str = ""
    title: str = ""
    year: str = ""
    media_type: str = "movie"
    imdb_rating: str = ""
    subtitle_types: List[str] = field(default_factory=list)
    url: str = ""
    cover_url: str = ""
    source: str = ""


@dataclass
class DownloadLinks:
    softsub: List[Dict] = field(default_factory=list)
    dubbed: List[Dict] = field(default_factory=list)
    nosub: List[Dict] = field(default_factory=list)
    cover_url: str = ""

    def any(self) -> bool:
        return bool(self.softsub or self.dubbed or self.nosub)


class BaseScraper(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    def base_url(self) -> str:
        return ""

    @property
    def enabled(self) -> bool:
        return True

    @abstractmethod
    async def search(self, query: str, page: int = 1) -> List[SearchResult]: ...

    @abstractmethod
    async def get_download_links(self, url_or_id: str) -> DownloadLinks: ...

    async def close(self):
        pass
