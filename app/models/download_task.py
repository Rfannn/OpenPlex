import datetime
from sqlalchemy import Integer, String, Float, DateTime, ForeignKey, Text, func, Boolean
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class DownloadTask(Base):
    __tablename__ = "download_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    catalog_id: Mapped[int] = mapped_column(Integer, ForeignKey("download_catalog.id", ondelete="SET NULL"), nullable=True)
    title: Mapped[str] = mapped_column(String(512), default="")
    url: Mapped[str] = mapped_column(Text, nullable=False)
    quality_label: Mapped[str] = mapped_column(String(128), default="")
    dest_path: Mapped[str] = mapped_column(String(1024), default="")
    file_name: Mapped[str] = mapped_column(String(512), default="")
    status: Mapped[str] = mapped_column(String(32), default="queued")
    progress_pct: Mapped[float] = mapped_column(Float, default=0.0)
    total_bytes: Mapped[str] = mapped_column(String(32), default="0")
    downloaded_bytes: Mapped[str] = mapped_column(String(32), default="0")
    speed: Mapped[str] = mapped_column(String(32), default="")
    error_message: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, server_default=func.now())
    completed_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=True)
    aria2_gid: Mapped[str] = mapped_column(String(64), default="")
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    scheduled_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=True)
    speed_limit: Mapped[str] = mapped_column(String(16), default="")
