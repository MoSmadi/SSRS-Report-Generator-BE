import os

from app import config

os.environ.setdefault("SQLSERVER_CONN_STR", "")
os.environ.setdefault("SQLSERVER_HOST", "")
os.environ.setdefault("SQLSERVER_DATABASE", "")
os.environ.setdefault("SQLSERVER_USER", "")
os.environ.setdefault("SQLSERVER_PASSWORD", "")
config.get_settings.cache_clear()

from app.main import app  # noqa: E402

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.mark.asyncio
async def test_health_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"ok": True}
