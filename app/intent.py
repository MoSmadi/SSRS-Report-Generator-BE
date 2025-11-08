"""Natural language intent parsing utilities."""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List

from .azure_openai import chat_completion, is_configured
from .schemas import ChartIntent, IntentFilter, NLSpec

logger = logging.getLogger(__name__)
SYSTEM_PROMPT = (
    "You convert a business reporting request into a structured spec. "
    "Return ONLY minified JSON matching the provided schema. Do not add prose."
)


def parse_intent(text: str, title: str) -> NLSpec:
    """Return an NLSpec using AOAI when available, rules otherwise."""
    title = title.strip() or "Untitled Report"
    cleaned_text = text.strip()
    if not cleaned_text:
        return parse_intent_rules(cleaned_text, title)

    if is_configured():
        try:
            spec = parse_intent_llm(cleaned_text, title)
            if spec:
                return spec
        except Exception as exc:  # pragma: no cover - depends on network
            logger.warning("AOAI intent parsing failed: %s", exc)
    return parse_intent_rules(cleaned_text, title)


def parse_intent_llm(text: str, title: str) -> NLSpec:
    """Use Azure OpenAI to extract a reporting spec."""
    schema_description = json.dumps(
        {
            "title": "string",
            "metrics": ["string"],
            "dimensions": ["string"],
            "filters": [{"field": "string", "operator": "string", "value": "string"}],
            "grain": "day|week|month|quarter|year|none",
            "chart": {"type": "table|line|bar|pie", "x": "string", "y": "string", "series": ["string"]},
        }
    )
    user_prompt = (
        f"TITLE: {title}\n"
        f"TEXT: {text}\n"
        f"JSON_SCHEMA: {schema_description}\n"
        "Return valid JSON."
    )
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]
    response = chat_completion(messages, response_format={"type": "json_object"})
    spec = NLSpec.model_validate_json(response)
    if not spec.title:
        spec.title = title
    return spec


def parse_intent_rules(text: str, title: str) -> NLSpec:
    """Deterministic fallback intent parsing."""
    lowered = text.lower()
    metrics = _extract_tokens(lowered, ["revenue", "sales", "amount", "profit", "count", "orders"])
    if not metrics:
        metrics.append("count")

    dimensions = _extract_tokens(lowered, ["region", "country", "product", "category", "channel", "segment", "customer"])
    grain = _detect_grain(lowered)

    filters: List[IntentFilter] = []
    date_matches = re.findall(r"(20\d{2}-\d{2}-\d{2})", text)
    if len(date_matches) >= 2:
        filters.append(IntentFilter(field="date", operator=">=", value=date_matches[0]))
        filters.append(IntentFilter(field="date", operator="<=", value=date_matches[1]))

    last_n_match = re.search(r"last (\d{1,2}) (day|week|month|quarter|year)s?", lowered)
    if last_n_match:
        unit = last_n_match.group(2)
        filters.append(IntentFilter(field="date", operator=">=", value=f"last_{unit}_{last_n_match.group(1)}"))

    region_match = re.search(r"in ([A-Za-z ]+)", text)
    if region_match:
        filters.append(
            IntentFilter(field="region", operator="in", value=",".join(tok.strip() for tok in region_match.group(1).split(" and ")))
        )

    chart = None
    if "trend" in lowered or grain in {"month", "quarter", "year"}:
        chart = ChartIntent(type="line", x=grain or "date", y=metrics[0], series=["region"] if "region" in dimensions else None)

    return NLSpec(
        title=title,
        metrics=metrics,
        dimensions=dimensions,
        filters=filters,
        grain=grain or "none",
        chart=chart,
    )


def spec_to_payload(spec: NLSpec) -> Dict[str, Any]:
    """Convert NLSpec to the API-facing spec dictionary."""
    filters_payload: List[Dict[str, str]] = []
    for flt in spec.filters:
        filters_payload.append(
            {
                "field": flt.field,
                "operator": flt.operator,
                "op": flt.operator,
                "value": flt.value,
            }
        )
    payload: Dict[str, any] = {
        "title": spec.title,
        "metrics": spec.metrics,
        "dimensions": spec.dimensions,
        "filters": filters_payload,
        "grain": None if spec.grain == "none" else spec.grain,
    }
    if spec.chart:
        payload["chart"] = spec.chart.model_dump(exclude_none=True)
    if spec.grain and spec.grain != "none":
        payload.setdefault("sort", [{"field": spec.grain, "dir": "asc"}])
    elif spec.metrics:
        payload.setdefault("sort", [{"field": spec.metrics[0], "dir": "desc"}])
    return payload


def _extract_tokens(text: str, keywords: List[str]) -> List[str]:
    tokens: List[str] = []
    for keyword in keywords:
        if keyword in text:
            tokens.append(keyword)
    return tokens


def _detect_grain(text: str) -> str:
    for candidate in ("day", "week", "month", "quarter", "year"):
        if re.search(rf"(per|by) {candidate}", text):
            return candidate
    return "month" if "monthly" in text else "none"
