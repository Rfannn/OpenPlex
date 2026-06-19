import datetime
from sqlalchemy import Integer, String, DateTime, func, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class CatalogFavorite(Base):
    """Watchlist item with status tracking."""
    __tablename__ = "catalog_favorite"
    __table_args__ = (UniqueConstraint("user_id", "catalog_id", name="uq_user_catalog_fav"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    catalog_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), default="want_to_watch")
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, server_default=func.now())
