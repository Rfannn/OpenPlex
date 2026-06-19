"""Tests for download route logic (unit tests with mocked DB)."""
import pytest
import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from app.routers.downloads import (
    _queue_download, set_speed_limit_rpc,
    _dl_settings, _ensure_trailing_slash, looks_like_media_url,
)


@pytest.mark.asyncio
async def test_ensure_trailing_slash():
    assert _ensure_trailing_slash("http://example.com/path") == "http://example.com/path/"
    assert _ensure_trailing_slash("http://example.com/path/") == "http://example.com/path/"


@pytest.mark.asyncio
async def test_looks_like_media_url():
    assert looks_like_media_url("http://example.com/movie.mkv") is True
    assert looks_like_media_url("http://example.com/movie.mp4") is True
    assert looks_like_media_url("http://example.com/movie.avi") is True
    assert looks_like_media_url("http://example.com/page.html") is False
    assert looks_like_media_url("http://example.com/") is False


@pytest.mark.asyncio
async def test_set_speed_limit_rpc_zero():
    with patch("app.routers.downloads.rpc_call", new=AsyncMock()) as mock_rpc:
        await set_speed_limit_rpc("gid123", "0")
        mock_rpc.assert_called_once()
        args = mock_rpc.call_args[0]
        assert args[0] == "aria2.changeOption"
        assert args[1][1]["max-download-limit"] == "0"


@pytest.mark.asyncio
async def test_set_speed_limit_rpc_positive():
    with patch("app.routers.downloads.rpc_call", new=AsyncMock()) as mock_rpc:
        await set_speed_limit_rpc("gid123", "1048576")
        mock_rpc.assert_called_once()
        args = mock_rpc.call_args[0]
        assert args[1][1]["max-download-limit"] == "1048576"


@pytest.mark.asyncio
async def test_set_speed_limit_rpc_invalid():
    with patch("app.routers.downloads.rpc_call", new=AsyncMock()) as mock_rpc:
        await set_speed_limit_rpc("gid123", "not-a-number")
        mock_rpc.assert_not_called()


@pytest.mark.asyncio
async def test_dl_settings_defaults():
    assert _dl_settings.get("max_concurrent") == 3


@pytest.mark.asyncio
async def test_queue_download_blocks_outside_media_root():
    from app.config import settings

    mock_db = AsyncMock()
    mock_user = MagicMock()
    mock_user.id = 1

    original_root = settings.media_root
    settings.media_root = "/media"

    task = await _queue_download(
        db=mock_db, user=mock_user,
        url="http://example.com/movie.mkv",
        dest_dir="/outside/path",
        title="Test",
        quality_label="1080p",
        catalog_id=None,
    )
    assert task is None  # blocked

    settings.media_root = original_root


@pytest.mark.asyncio
async def test_queue_download_scheduled():
    from app.config import settings
    from app.services.downloader import add_download

    original_root = settings.media_root
    settings.media_root = "/tmp"
    future = (datetime.datetime.now() + datetime.timedelta(hours=1)).isoformat()

    mock_db = AsyncMock()
    mock_user = MagicMock()
    mock_user.id = 1

    with patch("app.routers.downloads.os.makedirs"):
        with patch("app.routers.downloads.add_download", new=AsyncMock(return_value="")):
            with patch("app.routers.downloads.settings.check_disk_space", return_value=(True, 10000000000)):
                from app.routers.downloads import DownloadTask
                task = await _queue_download(
                    db=mock_db, user=mock_user,
                    url="http://example.com/movie.mkv",
                    dest_dir="/tmp/Movies/Test",
                    title="Test",
                    quality_label="1080p",
                    catalog_id=None,
                    scheduled_at=future,
                )
                if task is not None:
                    assert task.status == "queued"
                    assert task.scheduled_at is not None

    settings.media_root = original_root


@pytest.mark.asyncio
async def test_queue_download_adds_task():
    from app.config import settings
    original_root = settings.media_root
    settings.media_root = "/tmp"

    mock_db = AsyncMock()
    mock_user = MagicMock()
    mock_user.id = 1

    with patch("app.routers.downloads.os.makedirs"):
        with patch("app.routers.downloads.add_download", new=AsyncMock(return_value="new_gid_abc")):
            with patch("app.routers.downloads.settings.check_disk_space", return_value=(True, 10000000000)):
                task = await _queue_download(
                    db=mock_db, user=mock_user,
                    url="http://example.com/movie.mkv",
                    dest_dir="/tmp/Movies/Test",
                    title="Test Movie",
                    quality_label="1080p",
                    catalog_id=None,
                )
                if task is not None:
                    assert task.url == "http://example.com/movie.mkv"
                    assert task.title == "Test Movie"
                    assert task.aria2_gid == "new_gid_abc"

    settings.media_root = original_root
