"""Schema-aware column mapping helpers."""
from __future__ import annotations

import json
import re
from typing import List, Optional, Sequence, Tuple

from rapidfuzz import fuzz

from . import azure_openai
from .schemas import ColumnMetadata, MissingFieldSuggestion, NLSpec, SchemaInsights, SuggestedMappingItem

TIME_TERMS = {"date", "day", "week", "month", "quarter", "year", "time"}


def map_terms(spec: NLSpec, columns: Sequence[ColumnMetadata]) -> List[SuggestedMappingItem]:
    """Return schema-aware mappings for metrics and dimensions."""
    mappings: List[SuggestedMappingItem] = []
    for term in spec.metrics:
        mappings.append(_map_single(term, "metric", columns))
    for term in spec.dimensions:
        mappings.append(_map_single(term, "dimension", columns))
    return mappings


def compute_schema_insights(spec: NLSpec, mappings: Sequence[SuggestedMappingItem], columns: Sequence[ColumnMetadata]) -> SchemaInsights:
    total_terms = len(spec.metrics) + len(spec.dimensions)
    matched = [item.term for item in mappings if item.column]
    missing: List[MissingFieldSuggestion] = []
    for item in mappings:
        if item.column:
            continue
        suggestions = _top_suggestions(item.term, columns, limit=3)
        missing.append(MissingFieldSuggestion(name=item.term, suggestions=suggestions))
    coverage = 0 if total_terms == 0 else round(100 * len(matched) / total_terms)
    return SchemaInsights(coveragePercent=coverage, matchedFields=matched, missingFields=missing)


def _map_single(term: str, role: str, columns: Sequence[ColumnMetadata]) -> SuggestedMappingItem:
    normalized_term = _normalize(term)
    pool = _filter_columns_for_role(role, normalized_term, columns)
    scored = [_score_column(normalized_term, col) for col in pool]
    scored.sort(key=lambda item: item[1], reverse=True)
    top_col, confidence = (scored[0] if scored else (None, 0.0))

    if top_col and azure_openai.is_configured() and len(scored) > 1:
        reranked = _rerank_with_llm(term, scored[:3])
        if reranked is not None:
            top_col, confidence = reranked

    if confidence < 0.4:
        return SuggestedMappingItem(
            term=term,
            role="metric" if role == "metric" else "dimension",
            column=None,
            confidence=round(confidence, 2),
            reason="No confident match found",
        )
    qualified = top_col.qualified_name
    reason = f"Matched column name '{top_col.column}'"
    if role == "metric" and not top_col.isNumeric:
        reason = f"Best available non-numeric column '{top_col.column}'"
    return SuggestedMappingItem(
        term=term,
        role="metric" if role == "metric" else "dimension",
        column=qualified,
        confidence=round(confidence, 2),
        reason=reason,
    )


def _filter_columns_for_role(role: str, term: str, columns: Sequence[ColumnMetadata]) -> List[ColumnMetadata]:
    if role == "metric":
        numeric_cols = [col for col in columns if col.isNumeric]
        return numeric_cols or list(columns)
    if any(token in term for token in TIME_TERMS):
        date_cols = [col for col in columns if col.isDateLike]
        return date_cols or list(columns)
    categorical = [col for col in columns if not col.isNumeric]
    return categorical or list(columns)


def _score_column(term: str, column: ColumnMetadata) -> Tuple[ColumnMetadata, float]:
    column_label = _normalize(column.qualified_name)
    table_label = _normalize(f"{column.schema} {column.table} {column.column}")
    score = max(fuzz.token_set_ratio(term, column_label), fuzz.token_set_ratio(term, table_label)) / 100
    return column, score


def _normalize(value: str) -> str:
    lowered = value.lower()
    lowered = re.sub(r"[\[\]\._]", " ", lowered)
    lowered = re.sub(r"[^a-z0-9 ]+", " ", lowered)
    return re.sub(r"\s+", " ", lowered).strip()


def _top_suggestions(term: str, columns: Sequence[ColumnMetadata], limit: int = 3) -> List[str]:
    normalized_term = _normalize(term)
    scored = sorted((_score_column(normalized_term, col) for col in columns), key=lambda item: item[1], reverse=True)
    return [item[0].qualified_name for item in scored[:limit] if item[1] > 0]


def _rerank_with_llm(term: str, candidates: Sequence[Tuple[ColumnMetadata, float]]) -> Optional[Tuple[ColumnMetadata, float]]:
    try:
        options = [
            {"index": idx, "name": cand[0].qualified_name if cand[0].name is None else cand[0].name, "score": round(cand[1], 2)}
            for idx, cand in enumerate(candidates)
        ]
        user_prompt = (
            "Term: {term}\n"
            "Candidates:\n"
            "{candidates}\n"
            'Return JSON like {"index":0}.'
        ).format(term=term, candidates=json.dumps(options))
        content = azure_openai.chat_completion(
            [
                {"role": "system", "content": "Pick the best matching column index. Respond with minified JSON only."},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
        )
        data = json.loads(content)
        idx = data.get("index")
        if isinstance(idx, int) and 0 <= idx < len(candidates):
            return candidates[idx]
    except Exception:  # pragma: no cover - best-effort rerank
        return None
    return None
