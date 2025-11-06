import os

from app import config

os.environ.setdefault("API_KEY", "test-key")
os.environ.setdefault("SQLSERVER_CONN_STR", "")
config.get_settings.cache_clear()

from app.main import app  # noqa: E402

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_endpoint():
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"ok": True}
