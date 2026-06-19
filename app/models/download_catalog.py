import datetime
from sqlalchemy import Integer, String, Text, Float, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class DownloadCatalog(Base):
    __tablename__ = "download_catalog"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    imdb_code: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    title_type: Mapped[str] = mapped_column(String(32), default="movie")
    year: Mapped[str] = mapped_column(String(16), default="")
    imdb_rating: Mapped[str] = mapped_column(String(8), default="")
    imdb_votes: Mapped[str] = mapped_column(String(32), default="")
    softsub_links: Mapped[str] = mapped_column(Text, default="[]")
    dubbed_links: Mapped[str] = mapped_column(Text, default="[]")
    nosub_links: Mapped[str] = mapped_column(Text, default="[]")
    has_seasons: Mapped[bool] = mapped_column(default=False)
    season_info: Mapped[str] = mapped_column(Text, default="{}")
    cover_url: Mapped[str] = mapped_column(Text, default="")
    # TMDB-enriched fields
    backdrop_url: Mapped[str] = mapped_column(Text, default="")
    overview: Mapped[str] = mapped_column(Text, default="")
    tagline: Mapped[str] = mapped_column(Text, default="")
    genres_json: Mapped[str] = mapped_column(Text, default="[]")
    runtime_min: Mapped[int] = mapped_column(Integer, default=0)
    cast_json: Mapped[str] = mapped_column(Text, default="[]")
    director: Mapped[str] = mapped_column(String(256), default="")
    tmdb_id: Mapped[int] = mapped_column(Integer, default=0)
    last_updated: Mapped[datetime.datetime] = mapped_column(DateTime, server_default=func.now())
