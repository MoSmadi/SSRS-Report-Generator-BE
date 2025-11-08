"""Lightweight Azure OpenAI client helpers."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import requests

from .config import get_settings


def is_configured() -> bool:
    settings = get_settings()
    return bool(settings.azure_openai_endpoint and settings.azure_openai_api_key and settings.azure_openai_deployment)


def chat_completion(messages: List[Dict[str, str]], *, response_format: Optional[Dict[str, Any]] = None, temperature: float = 0.0) -> str:
    """Call Azure OpenAI chat completions and return the message content."""
    settings = get_settings()
    if not is_configured():
        raise RuntimeError("Azure OpenAI is not configured")

    url = (
        f"{settings.azure_openai_endpoint}openai/deployments/{settings.azure_openai_deployment}/chat/completions"
        "?api-version=2023-12-01-preview"
    )
    headers = {
        "api-key": settings.azure_openai_api_key,
        "Content-Type": "application/json",
    }
    payload: Dict[str, Any] = {"messages": messages, "temperature": temperature}
    if response_format is not None:
        payload["response_format"] = response_format
    response = requests.post(url, json=payload, headers=headers, timeout=20)
    response.raise_for_status()
    data = response.json()
    return data.get("choices", [{}])[0].get("message", {}).get("content", "") or ""
