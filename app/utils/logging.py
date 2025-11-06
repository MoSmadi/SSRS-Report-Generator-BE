"""Logging helpers that emit JSON per-request records."""
from __future__ import annotations

import json
import logging
import sys
from typing import Any

from starlette.requests import Request


class JsonRequestFormatter(logging.Formatter):
    """Formatter that renders structured JSON log records."""

    def format(self, record: logging.LogRecord) -> str:  # pragma: no cover - exercised via logging
        payload: dict[str, Any] = {
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
        }
        for attr in ("request_id", "path", "method", "status_code"):
            value = getattr(record, attr, None)
            if value is not None:
                payload[attr] = value
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def configure_logging(level: str = "INFO") -> None:
    """Configure root logging handler once for the process."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonRequestFormatter())
    logging.basicConfig(handlers=[handler], level=level, force=True)


def bind_request_context(request: Request) -> dict[str, Any]:
    """Return context dict used to enrich log records inside request scope."""
    return {
        "request_id": request.state.request_id,
        "path": request.url.path,
        "method": request.method,
    }
