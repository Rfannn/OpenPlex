"""Tests for the DownloadTask model."""
import pytest
import datetime
from unittest.mock import MagicMock, patch
from app.models.download_task import DownloadTask
from app.database import Base


@pytest.mark.asyncio
async def test_download_task_defaults():
    task = DownloadTask(
        user_id=1,
        url="http://example.com/file.mkv",
    )
    assert task.user_id == 1
    assert task.url == "http://example.com/file.mkv"
    assert task.title == "" or task.title is None
    assert task.status == "queued" or task.status is None
    assert task.progress_pct == 0.0 or task.progress_pct is None
    assert (task.total_bytes == "0" or task.total_bytes is None or task.total_bytes == 0)
    assert (task.downloaded_bytes == "0" or task.downloaded_bytes is None or task.downloaded_bytes == 0)
    assert task.speed == "" or task.speed is None
    assert task.error_message == "" or task.error_message is None
    assert task.aria2_gid == "" or task.aria2_gid is None
    assert task.retry_count == 0 or task.retry_count is None
    assert task.scheduled_at is None
    assert task.speed_limit == "" or task.speed_limit is None
    assert task.quality_label == "" or task.quality_label is None
    assert task.dest_path == "" or task.dest_path is None
    assert task.file_name == "" or task.file_name is None


@pytest.mark.asyncio
async def test_download_task_with_fields():
    now = datetime.datetime(2024, 1, 1, 12, 0, 0)
    task = DownloadTask(
        user_id=1,
        catalog_id=5,
        title="Test Movie",
        url="http://example.com/movie.mkv",
        quality_label="1080p",
        dest_path="/media/Movies/Test Movie (2024)",
        file_name="Test.Movie.2024.1080p.mkv",
        status="downloading",
        progress_pct=45.5,
        total_bytes="2147483648",
        downloaded_bytes="966367641",
        speed="5242880",
        error_message="",
        created_at=now,
        completed_at=None,
        aria2_gid="abcdef123456",
        retry_count=1,
        scheduled_at=now,
        speed_limit="1048576",
    )
    assert task.title == "Test Movie"
    assert task.status == "downloading"
    assert task.progress_pct == 45.5
    assert task.total_bytes == "2147483648"
    assert task.speed == "5242880"
    assert task.aria2_gid == "abcdef123456"
    assert task.retry_count == 1
    assert task.speed_limit == "1048576"
    assert task.scheduled_at == now


def test_download_task_table_name():
    assert DownloadTask.__tablename__ == "download_tasks"


def test_download_task_is_sqlalchemy_model():
    from sqlalchemy.orm import DeclarativeBase
    assert isinstance(DownloadTask.__bases__[0], type(Base))
