"""Natural language intent parsing utilities."""
from __future__ import annotations

import re
from typing import Any

import requests

from . import catalog
from .config import get_settings
from .schemas import InferOut, Mapping


def parse_intent(text: str) -> dict:
    """Return a deterministic spec extracted from the NL request."""
    lowered = text.lower()
    metrics = []
    for token in ("revenue", "sales", "count", "orders", "profit"):
        if token in lowered:
            metrics.append(token)
    if not metrics:
        metrics.append("count")

    dims = []
    for token in ("region", "country", "product", "category", "channel"):
        if token in lowered:
            dims.append(token)

    grain = None
    for candidate in ("day", "week", "month", "quarter", "year"):
        if re.search(rf"per {candidate}|by {candidate}", lowered):
            grain = candidate
            break

    filters = []
    date_matches = re.findall(r"(\d{4}-\d{2}-\d{2})", text)
    if len(date_matches) >= 2:
        filters.append({"field": "OrderDate", "op": ">=", "value": date_matches[0]})
        filters.append({"field": "OrderDate", "op": "<=", "value": date_matches[1]})

    region_match = re.search(r"in ([A-Za-z ]+)", text)
    if region_match:
        filters.append(
            {
                "field": "Region",
                "op": "=",
                "value": region_match.group(1).strip().title(),
            }
        )

    chart = None
    if "trend" in lowered or (grain in {"month", "quarter", "year"} and metrics):
        chart = {"type": "line", "values": metrics, "category": grain or "OrderDate"}

    return {
        "title": text.strip()[:80],
        "metrics": metrics,
        "dimensions": dims,
        "grain": grain,
        "filters": filters,
        "chart": chart,
        "sort": [{"field": metrics[0], "dir": "desc"}],
    }


def _call_azure_openai(prompt: str) -> str:
    settings = get_settings()
    if not (settings.azure_openai_endpoint and settings.azure_openai_api_key and settings.azure_openai_deployment):
        return ""

    url = f"{settings.azure_openai_endpoint}openai/deployments/{settings.azure_openai_deployment}/chat/completions?api-version=2023-12-01-preview"
    headers = {
        "api-key": settings.azure_openai_api_key,
        "Content-Type": "application/json",
    }
    payload = {
        "messages": [
            {"role": "system", "content": "You map business terms to columns."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0,
    }
    resp = requests.post(url, json=payload, headers=headers, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    return data.get("choices", [{}])[0].get("message", {}).get("content", "")


def _heuristic_mapping(columns: list[dict], spec: dict) -> list[Mapping]:
    results: list[Mapping] = []
    for term in spec["metrics"] + spec["dimensions"]:
        match = next((col for col in columns if term.lower() in col["name"].lower()), None)
        if match:
            results.append(
                Mapping(
                    term=term,
                    column=match["name"],
                    role="measure" if term in spec["metrics"] else "dimension",
                )
            )
    return results


def infer_from_nl(db: str, title: str, text: str) -> InferOut:
    settings = get_settings()
    spec = parse_intent(text)
    spec["title"] = title or spec["title"]
    available_columns = catalog.list_columns(db)
    suggested = _heuristic_mapping(available_columns, spec)
    notes = ""
    if settings.azure_openai_api_key:
        try:
            notes = _call_azure_openai(
                f"Suggest mappings for: {text}. Columns: {[c['name'] for c in available_columns]}"
            )
        except requests.RequestException as exc:  # pragma: no cover - network only
            notes = f"Azure OpenAI call failed: {exc}"[:200]
    return InferOut(spec=spec, suggestedMapping=suggested, availableColumns=available_columns, notes=notes or None)
