"""API key enforcement utilities."""
from __future__ import annotations

from fastapi import Depends, Header, HTTPException, status

from ..config import get_settings


def require_api_key(x_api_key: str | None = Header(None, alias="X-API-Key")) -> None:
    settings = get_settings()
    if not settings.api_key:
        return
    if x_api_key != settings.api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"message": "Missing or invalid API key", "code": "unauthorized"}},
        )


def secure_dependency() -> Depends:  # pragma: no cover - FastAPI wiring helper
    return Depends(require_api_key)
