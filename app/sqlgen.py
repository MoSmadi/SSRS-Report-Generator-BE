"""SQL text generation based on inferred intent and mappings."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from .schemas import Mapping

TIME_GRAINS = {
    "day": "CAST({col} AS DATE)",
    "week": "DATEADD(day, -DATEPART(weekday, {col}) + 1, CAST({col} AS DATE))",
    "month": "DATEFROMPARTS(YEAR({col}), MONTH({col}), 1)",
    "quarter": "DATEFROMPARTS(YEAR({col}), ((DATEPART(quarter, {col})-1)*3)+1, 1)",
    "year": "DATEFROMPARTS(YEAR({col}), 1, 1)",
}


def _time_bucket(column: Optional[str], grain: Optional[str]) -> Tuple[str, Optional[str]]:
    if not column:
        return "OrderDate", None
    if not grain:
        return column, None
    template = TIME_GRAINS.get(grain)
    if not template:
        return column, None
    bucket = template.format(col=column)
    return bucket, f"{grain.title()}Bucket"


def _resolve_from_table(mapping: List[Mapping]) -> str:
    for map_item in mapping:
        if not map_item.column:
            continue
        parts = _plain_column(map_item.column).split(".")
        if len(parts) >= 2:
            return ".".join(parts[:-1])
    return "dbo.FactSales"


def _infer_param_type(field_name: str) -> str:
    lowered = field_name.lower()
    if "date" in lowered or "time" in lowered:
        return "DateTime"
    if "amount" in lowered or "qty" in lowered or "count" in lowered:
        return "Float"
    return "String"


def _plain_column(column: str) -> str:
    cleaned = column.replace("[", "").replace("]", "")
    cleaned = cleaned.replace("].[", ".")
    cleaned = cleaned.replace("].", ".").replace(".[", ".")
    return cleaned


def _column_alias(column: str) -> str:
    plain = _plain_column(column)
    return plain.split(".")[-1]


def build_sql(spec: Dict[str, Any], mapping: List[Mapping]) -> Tuple[str, List[Dict[str, Any]]]:
    dims: List[str] = [m.column for m in mapping if m.role in {"dimension"} and m.column]
    measures: List[str] = [m.column for m in mapping if m.role in {"measure", "metric"} and m.column]
    time_mapping = next((m.column for m in mapping if m.role == "time" and m.column), None)

    select_parts: List[str] = []
    group_parts: List[str] = []

    bucket_expr, bucket_alias = _time_bucket(time_mapping, spec.get("grain"))
    if bucket_alias:
        select_parts.append(f"{bucket_expr} AS [{bucket_alias}]")
        group_parts.append(bucket_expr)
    elif time_mapping:
        select_parts.append(f"{time_mapping} AS [{time_mapping.rsplit('.', 1)[-1]}]")
        group_parts.append(time_mapping)

    for dim in dims:
        alias = _column_alias(dim)
        select_parts.append(f"{dim} AS [{alias}]")
        group_parts.append(dim)

    if measures:
        for measure in measures:
            alias = _column_alias(measure)
            select_parts.append(f"SUM({measure}) AS [{alias}]")
    else:
        select_parts.append("COUNT(1) AS [RowCount]")

    filters = spec.get("filters", [])
    where_clauses: List[str] = []
    params: List[Dict[str, Any]] = []
    for filter_def in filters:
        field = filter_def.get("field", "1")
        op = filter_def.get("op", "=")
        raw_name = filter_def.get("param") or field
        param_name = f"@{raw_name}".replace(".", "")
        where_clauses.append(f"{field} {op} {param_name}")
        params.append({"name": param_name, "rdlType": _infer_param_type(field), "value": filter_def.get("value")})

    from_table = spec.get("from") or _resolve_from_table(mapping)

    select_clause = "    " + ",\n    ".join(select_parts) if select_parts else "    1"
    sql_lines = ["SELECT", select_clause, f"FROM {from_table}"]
    if where_clauses:
        sql_lines.append("WHERE " + " AND ".join(where_clauses))
    if group_parts:
        sql_lines.append("GROUP BY " + ", ".join(group_parts))
    if spec.get("sort"):
        sort_clause = ", ".join(f"{item['field']} {item.get('dir', 'asc').upper()}" for item in spec["sort"])
        sql_lines.append(f"ORDER BY {sort_clause}")

    return "\n".join(sql_lines), params
