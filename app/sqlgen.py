"""SQL text generation based on inferred intent and mappings."""
from __future__ import annotations

from typing import Any

from .schemas import Mapping

TIME_GRAINS = {
    "day": "CAST({col} AS DATE)",
    "week": "DATEADD(day, -DATEPART(weekday, {col}) + 1, CAST({col} AS DATE))",
    "month": "DATEFROMPARTS(YEAR({col}), MONTH({col}), 1)",
    "quarter": "DATEFROMPARTS(YEAR({col}), ((DATEPART(quarter, {col})-1)*3)+1, 1)",
    "year": "DATEFROMPARTS(YEAR({col}), 1, 1)",
}


def _time_bucket(column: str | None, grain: str | None) -> tuple[str, str | None]:
    if not column:
        return column or "OrderDate", None
    if not grain:
        return column, None
    template = TIME_GRAINS.get(grain)
    if not template:
        return column, None
    bucket = template.format(col=column)
    return bucket, f"{grain.title()}Bucket"


def _resolve_from_table(mapping: list[Mapping]) -> str:
    for map_item in mapping:
        if "." in map_item.column:
            return map_item.column.rsplit(".", 1)[0]
    return "dbo.FactSales"


def _infer_param_type(field_name: str) -> str:
    lowered = field_name.lower()
    if "date" in lowered or "time" in lowered:
        return "DateTime"
    if "amount" in lowered or "qty" in lowered or "count" in lowered:
        return "Float"
    return "String"


def build_sql(spec: dict, mapping: list[Mapping]) -> tuple[str, list[dict[str, Any]]]:
    dims: list[str] = [m.column for m in mapping if m.role == "dimension"]
    measures: list[str] = [m.column for m in mapping if m.role == "measure"]
    time_mapping = next((m.column for m in mapping if m.role == "time"), None)

    select_parts: list[str] = []
    group_parts: list[str] = []

    bucket_expr, bucket_alias = _time_bucket(time_mapping, spec.get("grain"))
    if bucket_alias:
        select_parts.append(f"{bucket_expr} AS [{bucket_alias}]")
        group_parts.append(bucket_expr)
    elif time_mapping:
        select_parts.append(f"{time_mapping} AS [{time_mapping.rsplit('.', 1)[-1]}]")
        group_parts.append(time_mapping)

    for dim in dims:
        alias = dim.rsplit(".", 1)[-1]
        select_parts.append(f"{dim} AS [{alias}]")
        group_parts.append(dim)

    if measures:
        for measure in measures:
            alias = measure.rsplit(".", 1)[-1]
            select_parts.append(f"SUM({measure}) AS [{alias}]")
    else:
        select_parts.append("COUNT(1) AS [RowCount]")

    filters = spec.get("filters", [])
    where_clauses = []
    params = []
    for f in filters:
        field = f.get("field", "1")
        op = f.get("op", "=")
        raw_name = f.get("param") or field
        param_name = f"@{raw_name}".replace(".", "")
        where_clauses.append(f"{field} {op} {param_name}")
        params.append({"name": param_name, "rdlType": _infer_param_type(field), "value": f.get("value")})

    from_table = spec.get("from") or _resolve_from_table(mapping)

    sql_lines = ["SELECT", "    " + ",\n    ".join(select_parts) if select_parts else "    1"]
    sql_lines.append(f"FROM {from_table}")
    if where_clauses:
        sql_lines.append("WHERE " + " AND ".join(where_clauses))
    if group_parts:
        sql_lines.append("GROUP BY " + ", ".join(group_parts))
    if spec.get("sort"):
        sort_clause = ", ".join(f\"{item['field']} {item.get('dir', 'asc').upper()}\" for item in spec[\"sort\"])
        sql_lines.append(f\"ORDER BY {sort_clause}\")

    return \"\\n\".join(sql_lines), params
