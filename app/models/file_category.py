import datetime
from typing import Optional
from sqlalchemy import String, Integer, Float, DateTime, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class FileCategory(Base):
    __tablename__ = "file_categories"

    file_path: Mapped[str] = mapped_column(String(1024), primary_key=True)
    category: Mapped[str] = mapped_column(String(64), default="other")
    genre: Mapped[str] = mapped_column(Text, default="[]")
    year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
