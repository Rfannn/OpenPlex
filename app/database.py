from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=5,
    connect_args={"check_same_thread": False},
)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db():
    async with engine.begin() as conn:
        from app.models import User, WatchHistory, DownloadCatalog, DownloadTask, CatalogFavorite, FileCategory
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text("PRAGMA journal_mode=WAL;"))
        await conn.execute(text("PRAGMA synchronous=NORMAL;"))

    async with engine.connect() as conn:
        for tbl_col in [
            ("download_catalog", "cover_url", "TEXT DEFAULT ''"),
            ("download_catalog", "backdrop_url", "TEXT DEFAULT ''"),
            ("download_catalog", "overview", "TEXT DEFAULT ''"),
            ("download_catalog", "tagline", "TEXT DEFAULT ''"),
            ("download_catalog", "genres_json", "TEXT DEFAULT '[]'"),
            ("download_catalog", "runtime_min", "INTEGER DEFAULT 0"),
            ("download_catalog", "cast_json", "TEXT DEFAULT '[]'"),
            ("download_catalog", "director", "VARCHAR(256) DEFAULT ''"),
            ("download_catalog", "tmdb_id", "INTEGER DEFAULT 0"),
            ("download_tasks", "retry_count", "INTEGER DEFAULT 0"),
            ("download_tasks", "scheduled_at", "DATETIME"),
            ("download_tasks", "speed_limit", "VARCHAR(16) DEFAULT ''"),
            ("catalog_favorite", "status", "VARCHAR(32) DEFAULT 'want_to_watch'"),
        ]:
            try:
                await conn.execute(text(f"ALTER TABLE {tbl_col[0]} ADD COLUMN {tbl_col[1]} {tbl_col[2]}"))
                await conn.commit()
            except Exception:
                await conn.rollback()

        # Performance indexes for frequently queried columns
        _indexes = [
            ("idx_download_tasks_user_id", "download_tasks", "user_id"),
            ("idx_download_tasks_status", "download_tasks", "status"),
            ("idx_download_catalog_title", "download_catalog", "title"),
            ("idx_download_catalog_imdb_code", "download_catalog", "imdb_code"),
            ("idx_download_catalog_title_type", "download_catalog", "title_type"),
            ("idx_watch_history_user_id", "watch_history", "user_id"),
            ("idx_catalog_favorite_user_id", "catalog_favorite", "user_id"),
            ("idx_catalog_favorite_catalog_id", "catalog_favorite", "catalog_id"),
            ("idx_file_categories_file_path", "file_categories", "file_path"),
        ]
        for idx_name, table, column in _indexes:
            try:
                await conn.execute(text(f"CREATE INDEX IF NOT EXISTS {idx_name} ON {table} ({column})"))
                await conn.commit()
            except Exception:
                await conn.rollback()
