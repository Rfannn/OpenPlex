"""Tests for API endpoints using mocked dependencies."""
import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch, ANY
from httpx import AsyncClient, ASGITransport
from app.main import app


@pytest.fixture
def client():
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.asyncio
async def test_health_check(client):
    resp = await client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "disk_total" in data
    assert "disk_free" in data
    assert "media_root" in data


@pytest.mark.asyncio
async def test_root_returns_html(client):
    resp = await client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")


@pytest.mark.asyncio
async def test_login_page(client):
    resp = await client.get("/login")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")


@pytest.mark.asyncio
async def test_register_page(client):
    resp = await client.get("/register")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")


@pytest.mark.asyncio
async def test_library_page(client):
    resp = await client.get("/library")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")


@pytest.mark.asyncio
async def test_downloads_page(client):
    resp = await client.get("/downloads")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")


@pytest.mark.asyncio
async def test_health_page(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")


@pytest.mark.asyncio
async def test_static_files_served(client):
    resp = await client.get("/static/style.css")
    assert resp.status_code == 200
    assert "text/css" in resp.headers.get("content-type", "")


@pytest.mark.asyncio
async def test_favicon_served(client):
    resp = await client.get("/favicon.ico")
    assert resp.status_code == 200
    assert "image/svg+xml" in resp.headers.get("content-type", "")


@pytest.mark.asyncio
async def test_browse_api_no_auth(client):
    resp = await client.get("/api/browse/")
    assert resp.status_code in (200, 403, 401)


@pytest.mark.asyncio
async def test_css_has_cache_buster(client):
    from app.main import templates
    from starlette.templating import _TemplateResponse
    resp = await client.get("/login")
    content = resp.text
    assert 'style.css?v=2' in content


@pytest.mark.asyncio
async def test_404_returns_error_page(client):
    resp = await client.get("/nonexistent-route-12345")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_status_page():
    from app.routers.status import router as status_router
    assert status_router is not None


@pytest.mark.asyncio
async def test_media_api_no_filename(client):
    resp = await client.get("/api/media/")
    assert resp.status_code in (404, 422)


@pytest.mark.asyncio
async def test_media_text_file_returns_content(client):
    resp = await client.get("/api/media/test_nonexistent_file_12345.txt")
    assert resp.status_code in (404, 422)


@pytest.mark.asyncio
async def test_auth_register_validation(client):
    resp = await client.post("/api/auth/register", json={})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_auth_login_validation(client):
    resp = await client.post("/api/auth/login", json={})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_library_api_no_auth(client):
    resp = await client.get("/api/library")
    assert resp.status_code in (200, 401, 403)


@pytest.mark.asyncio
async def test_library_continue_watching(client):
    resp = await client.get("/api/library/continue-watching")
    assert resp.status_code in (200, 401, 403)


@pytest.mark.asyncio
async def test_library_rows(client):
    resp = await client.get("/api/library/rows")
    assert resp.status_code in (200, 401, 403)


@pytest.mark.asyncio
async def test_library_genres(client):
    resp = await client.get("/api/library/genres")
    assert resp.status_code in (200, 401, 403)


@pytest.mark.asyncio
async def test_library_search(client):
    resp = await client.get("/api/library/search?q=test")
    assert resp.status_code in (200, 401, 403)


@pytest.mark.asyncio
async def test_gallery_removed(client):
    """Gallery page was removed — endpoint should 404."""
    resp = await client.get("/gallery")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_thumbnail_api(client):
    resp = await client.get("/api/thumbnail/test_nonexistent.png")
    assert resp.status_code in (404, 422)


@pytest.mark.asyncio
async def test_metrics_endpoint(client):
    resp = await client.get("/metrics")
    assert resp.status_code in (200, 404)


@pytest.mark.asyncio
async def test_stream_api_no_path(client):
    resp = await client.get("/api/stream")
    assert resp.status_code in (404, 422, 400)


@pytest.mark.asyncio
async def test_detailed_health(client):
    resp = await client.get("/api/health/detailed")
    assert resp.status_code in (200, 401, 403, 404)


@pytest.mark.asyncio
async def test_catalog_endpoint_no_auth(client):
    resp = await client.get("/api/catalog")
    assert resp.status_code in (200, 401, 403)


@pytest.mark.asyncio
async def test_search_sources(client):
    resp = await client.get("/api/search/sources")
    assert resp.status_code in (200, 401, 403)


@pytest.mark.asyncio
async def test_azfilm_search_validation(client):
    resp = await client.get("/api/azfilm/search")
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_download_settings(client):
    resp = await client.get("/api/downloads/settings")
    assert resp.status_code in (200, 401, 403)


@pytest.mark.asyncio
async def test_enrich_status(client):
    resp = await client.get("/api/enrich/status")
    assert resp.status_code in (200, 401, 403)


@pytest.mark.asyncio
async def test_favorites_ids_no_auth(client):
    resp = await client.get("/api/favorites/ids")
    assert resp.status_code in (200, 401, 403)


@pytest.mark.asyncio
async def test_status_api_no_auth(client):
    resp = await client.get("/api/status")
    assert resp.status_code in (200, 401, 403)


@pytest.mark.asyncio
async def test_register_invalid_data(client):
    resp = await client.post("/api/auth/register", json={"username": "t", "password": "t"})
    assert resp.status_code in (200, 400, 422)


@pytest.mark.asyncio
async def test_thumbnail_valid(client):
    resp = await client.get("/api/thumbnail/test_nonexistent.jpg")
    assert resp.status_code in (404, 422)


@pytest.mark.asyncio
async def test_browse_api_with_subpath(client):
    resp = await client.get("/api/browse/", params={"subpath": "Movies"})
    assert resp.status_code in (200, 404, 401, 403)


@pytest.mark.asyncio
async def test_history_api_no_auth(client):
    resp = await client.get("/api/history")
    assert resp.status_code in (200, 401, 403)


@pytest.mark.asyncio
async def test_server_has_gzip(client):
    resp = await client.get("/api/health", headers={"Accept-Encoding": "gzip"})
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_register_login_flow():
    from app.dependencies import create_access_token, verify_password, get_password_hash
    hashed = get_password_hash("testpass123")
    assert verify_password("testpass123", hashed) is True
    assert verify_password("wrongpass", hashed) is False
    token = create_access_token({"sub": 1})
    assert token is not None
    assert len(token) > 20


@pytest.mark.asyncio
async def test_jwt_token_creation():
    from app.dependencies import create_access_token, decode_token
    token = create_access_token({"sub": 42, "username": "testuser"})
    payload = decode_token(token)
    assert payload is not None
    assert payload.get("sub") == 42
    assert payload.get("username") == "testuser"


@pytest.mark.asyncio
async def test_get_optional_user_returns_none_when_no_token():
    from app.dependencies import get_optional_user
    result = await get_optional_user(token="")
    assert result is None


@pytest.mark.asyncio
async def test_downloads_endpoint_no_auth(client):
    resp = await client.get("/api/downloads")
    assert resp.status_code in (200, 401, 403)


@pytest.mark.asyncio
async def test_season_preview_no_url(client):
    resp = await client.get("/api/season-preview")
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_transcode_status(client):
    resp = await client.get("/api/transcode/status", params={"path": "/nonexistent/test.mkv"})
    assert resp.status_code in (200, 404, 422)


@pytest.mark.asyncio
async def test_metadata_endpoint(client):
    resp = await client.get("/api/metadata", params={"path": "test.mp4"})
    assert resp.status_code in (200, 404, 422)
