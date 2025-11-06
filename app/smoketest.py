"""Utilities for constructing user-facing smoke-test URLs."""
from __future__ import annotations

from urllib.parse import urlencode, quote

from .config import get_settings


def make_render_url(item_path: str, default_params: dict[str, str] | None = None) -> str:
    settings = get_settings()
    base = settings.render_base.rstrip("/")
    path = item_path if item_path.startswith("/") else f"/{item_path}"
    query_items = [("rs:Command", "Render"), ("rs:Format", "PDF")]
    for key, value in (default_params or {}).items():
        query_items.append((key, value))
    query = urlencode(query_items, doseq=True)
    return f"{base}?{quote(path, safe='/')}" + (f"&{query}" if query else "")
