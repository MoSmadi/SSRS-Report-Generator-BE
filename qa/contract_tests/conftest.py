from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
import requests

ENV_PATH = Path(__file__).resolve().parents[1] / ".env"
DEFAULTS = {
    "API_BASE": "http://localhost:8000",
    "TEST_REPORT_TITLE": "Contract Test Report",
    "TEST_PROMPT": "total sales by month and region",
}

if ENV_PATH.exists():
    for line in ENV_PATH.read_text().splitlines():
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


@dataclass
class ApiClient:
    base_url: str

    def request(self, method: str, path: str, **kwargs: Any) -> requests.Response:
        url = f"{self.base_url.rstrip('/')}{path}"
        headers = kwargs.pop("headers", {})
        headers.setdefault("Content-Type", "application/json")
        try:
            response = requests.request(method, url, headers=headers, timeout=10, **kwargs)
        except requests.RequestException as exc:  # pragma: no cover - network only
            raise RuntimeError(f"HTTP {method} {url} failed: {exc}") from exc
        return response

    def get_json(self, path: str, **kwargs: Any) -> dict[str, Any]:
        response = self.request("GET", path, **kwargs)
        try:
            data = response.json()
        except ValueError as exc:  # pragma: no cover
            raise AssertionError(f"Non-JSON response from {path}: {response.text}") from exc
        return data

    def post_json(self, path: str, **kwargs: Any) -> tuple[requests.Response, dict[str, Any]]:
        response = self.request("POST", path, **kwargs)
        try:
            data = response.json()
        except ValueError:  # pragma: no cover
            data = {}
        return response, data


@pytest.fixture(scope="session")
def api() -> ApiClient:
    base = os.getenv("API_BASE", DEFAULTS["API_BASE"])
    return ApiClient(base_url=base)


@pytest.fixture(scope="session")
def first_database(api: ApiClient) -> str:
    response = api.request("GET", "/report/customerDatabases")
    assert response.status_code == 200, f"Unexpected status: {response.status_code} {response.text}"
    data = response.json()
    databases = data.get("databases") or []
    if not databases:
        pytest.fail("No databases available from /report/customerDatabases")
    return databases[0]["name"]


def require_success(response: requests.Response, data: dict[str, Any], message: str) -> dict[str, Any]:
    if response.status_code != 200:
        raise AssertionError(f"{message}: {response.status_code} {json.dumps(data)}")
    return data
