"""Lightweight SSRS REST API helpers."""
from __future__ import annotations

from urllib.parse import quote

import requests

from .config import get_settings


def _base_url() -> str:
    base = get_settings().render_base.rstrip("/")
    return f"{base}/reports/api/v2.0"


def get_system_info() -> dict | None:
    try:
        resp = requests.get(f"{_base_url()}/SystemInfo", timeout=10)
        if resp.ok:
            return resp.json()
    except requests.RequestException:  # pragma: no cover - network only
        return None
    return None


def set_report_datasources(report_path_or_id: str, refs: list[dict]) -> bool:
    payload = {"DataSources": refs}
    candidates = [
        f"{_base_url()}/Reports({report_path_or_id})/DataSources",
        f"{_base_url()}/Reports(Path='{quote(report_path_or_id, safe='/')}')/DataSources",
    ]
    for url in candidates:
        try:
            resp = requests.put(url, json=payload, timeout=10)
            if resp.ok:
                return True
        except requests.RequestException:  # pragma: no cover
            continue
    return False
