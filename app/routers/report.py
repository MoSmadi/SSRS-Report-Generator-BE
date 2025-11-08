"""Report-related API endpoints."""
from __future__ import annotations

import contextlib
import json
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from fastapi.encoders import jsonable_encoder

from .. import catalog, sqlgen
from ..config import get_settings
from ..intent import parse_intent, spec_to_payload
from ..mapping import compute_schema_insights, map_terms
from ..db import open_sql_connection, sql_connection_available
from ..models import ServiceError
from ..rdl import build_rdl
from ..schemas import (
    ColumnDef,
    FilterDef,
    GenSQLIn,
    GenSQLOut,
    InferIn,
    InferOut,
    PreviewIn,
    PreviewOut,
    PublishIn,
    PublishOut,
    SortDef,
)
from ..smoketest import make_render_url
from ..ssrs_rest import get_system_info, set_report_datasources
from ..ssrs_soap import set_shared_datasource, upload_rdl

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter(prefix="/report", tags=["reports"])


@router.get("/customerDatabases")
def list_databases() -> Dict[str, List[Dict[str, str]]]:
    _log_api_event("customerDatabases.request", None)
    try:
        databases = catalog.list_databases()
    except Exception as exc:  # pragma: no cover - requires DB
        logger.exception("failed to list databases")
        detail = _summarize_error(exc)
        message = "Unable to list databases"
        if detail:
            message = f"{message}: {detail}"
        raise ServiceError(message, "catalog_error", status_code=502) from exc
    response = {"databases": databases}
    _log_api_event("customerDatabases.response", response)
    return response


@router.post("/inferFromNaturalLanguage", response_model=InferOut)
def infer_from_nl(payload: Dict[str, Any]) -> Dict[str, Any]:
    db = payload.get("db") or payload.get("databaseName")
    text = payload.get("text") or payload.get("request")
    title = payload.get("title") or ""
    if not db or not text:
        raise HTTPException(status_code=400, detail="db and text are required")

    spec_model = parse_intent(text, title)
    spec_payload = spec_to_payload(spec_model)

    try:
        columns = catalog.list_columns(db)
    except Exception as exc:  # pragma: no cover - DB failure path
        logger.warning("Failed to load columns for %s: %s", db, exc)
        columns = catalog.demo_columns()

    suggested = map_terms(spec_model, columns)
    insights = compute_schema_insights(spec_model, suggested, columns)

    response = {
        "spec": spec_payload,
        "suggestedMapping": [item.model_dump(exclude_none=True) for item in suggested],
        "availableColumns": [col.model_dump(exclude_none=True) for col in columns],
        "schemaInsights": insights.model_dump(),
    }
    _log_api_event("inferFromNaturalLanguage.response", response)
    logger.info(
        "infer.intent",
        extra={"db": db, "title": spec_model.title, "coveragePercent": insights.coveragePercent},
    )
    logger.debug("infer.mapping", extra={"mappings": response["suggestedMapping"]})
    return response


@router.post("/generateSQL", response_model=GenSQLOut)
def generate_sql(payload: GenSQLIn) -> GenSQLOut:
    _log_api_event("generateSQL.request", payload)
    mapping_payload = [m.model_dump() for m in payload.mapping]
    logger.debug(
        "generateSQL.payload",
        extra={
            "db": payload.db,
            "spec": payload.spec,
            "mapping": mapping_payload,
        },
    )

    valid_mapping = [m for m in payload.mapping if m.column]
    if not valid_mapping:
        raise ServiceError("At least one mapped column is required", "invalid_mapping", status_code=400)

    sql_text, params = sqlgen.build_sql(payload.spec, valid_mapping)
    logger.debug("generateSQL.sql", extra={"sql": sql_text, "db": payload.db})
    try:
        columns_meta = catalog.validate_shape(sql_text)
    except Exception as exc:  # pragma: no cover - DB only
        logger.exception(
            "failed to validate SQL shape",
            extra={"sql": sql_text, "db": payload.db, "spec": payload.spec, "mapping": mapping_payload},
        )
        detail = _summarize_error(exc)
        message = "Unable to validate SQL output"
        if detail:
            message = f"{message}: {detail}"
        raise ServiceError(message, "catalog_error", status_code=502) from exc

    column_defs: List[ColumnDef] = []
    for meta in columns_meta:
        samples = None
        with contextlib.suppress(Exception):
            if "." in meta["name"]:
                samples = catalog.sample_values(payload.db, meta["name"])
        rdl_type = meta.get("rdlType", "String")
        if rdl_type == "Float":
            role = "measure"
        elif rdl_type == "DateTime":
            role = "time"
        else:
            role = "dimension"
        column_defs.append(
            ColumnDef(
                name=meta["name"],
                source=meta.get("source", meta["name"]),
                system_type_name=meta.get("system_type_name"),
                rdlType=rdl_type,
                role=role,
                display_name=meta["name"],
                samples=samples,
                null_pct=None,
            )
        )

    response = GenSQLOut(sql=sql_text, params=params, columns=column_defs)
    _log_api_event("generateSQL.response", response)
    return response


@router.post("/preview", response_model=PreviewOut)
def preview(payload: PreviewIn) -> PreviewOut:
    _log_api_event("preview.request", payload)
    limit = payload.limit or 100
    limit = max(1, min(limit, 500))
    rows: List[Dict[str, Any]]
    if not sql_connection_available():
        rows = [{"message": "Preview unavailable in this environment"}]
        response = PreviewOut(rows=rows[:limit], row_count=len(rows))
        _log_api_event("preview.response", response)
        return response

    params = payload.params or {}
    declares: List[str] = []
    values: List[Any] = []
    for key, value in params.items():
        param_name = key if key.startswith("@") else f"@{key}"
        declares.append(f"DECLARE {param_name} NVARCHAR(4000) = ?;")
        values.append(value)

    base_sql, _ = _split_order_by_clause(payload.sql)
    limited_sql = f"SELECT TOP {limit} * FROM (\n{base_sql}\n) AS src"
    sql_text = "\n".join(declares + [limited_sql])

    try:
        with contextlib.closing(open_sql_connection(payload.db)) as conn:
            cursor = conn.cursor()
            cursor.execute(sql_text, values)
            columns = [col[0] for col in cursor.description]
            rows = [dict(zip(columns, row)) for row in cursor.fetchmany(limit)]
    except Exception as exc:  # pragma: no cover - DB specific
        logger.exception("preview execution failed", extra={"db": payload.db})
        detail = _summarize_error(exc)
        message = "Preview query failed"
        if detail:
            message = f"{message}: {detail}"
        raise ServiceError(message, "preview_error", status_code=400) from exc
    response = PreviewOut(rows=rows, row_count=len(rows))
    _log_api_event("preview.response", response)
    return response


@router.post("/publishReport", response_model=PublishOut)
def publish_report(payload: PublishIn) -> PublishOut:
    _log_api_event("publishReport.request", payload)
    dataset_name = payload.report.title.replace(" ", "") or "Dataset"
    sql_text = _build_publish_sql(payload.columns, payload.filters, payload.sort)
    rdl_bytes = build_rdl(
        namespace="http://schemas.microsoft.com/sqlserver/reporting/2016/01/reportdefinition",
        ds_name="MainDataSource",
        shared_ds_path=payload.report.shared_data_source_path,
        dataset_name=dataset_name,
        sql_text=sql_text,
        parameters=payload.parameters,
        fields=payload.columns,
        chart=payload.chart,
    )

    try:
        upload_result = upload_rdl(payload.report.folder, payload.report.title, rdl_bytes)
        set_shared_datasource(upload_result["path"], "MainDataSource", payload.report.shared_data_source_path)
        with contextlib.suppress(Exception):  # pragma: no cover - best effort
            set_report_datasources(
                upload_result["path"],
                [{"Id": "MainDataSource", "Name": "MainDataSource", "DataSourceId": payload.report.shared_data_source_path}],
            )
    except Exception as exc:  # pragma: no cover - network only
        raise ServiceError(f"Failed to publish report: {exc}", "ssrs_upload_failed", status_code=502) from exc

    render_url = make_render_url(upload_result["path"], {param.name: str(param.default or "") for param in payload.parameters})
    server_info = get_system_info() or {"status": "unknown"}

    response = PublishOut(
        path=upload_result["path"],
        render_url_pdf=render_url,
        server=server_info,
        dataset_fields=[field.model_dump() for field in payload.columns],
        echo=payload.model_dump(),
    )
    _log_api_event("publishReport.response", response)
    return response


def _build_publish_sql(
    columns: List[ColumnDef],
    filters: List[FilterDef],
    sort: Optional[List[SortDef]],
) -> str:
    if not columns:
        return "SELECT 1 AS Placeholder"

    select_parts = []
    table = None
    for column in columns:
        if column.source:
            select_parts.append(f"{column.source} AS [{column.name}]")
            if table is None:
                table = column.source.rsplit(".", 1)[0]
    select_clause = ", ".join(select_parts) if select_parts else "1 AS Placeholder"
    from_clause = table or "dbo.FactSales"

    sql_lines = ["SELECT", f"    {select_clause}", f"FROM {from_clause}"]

    if filters:
        filter_clauses = [f"{flt.field} {flt.op} @{flt.param}" for flt in filters]
        sql_lines.append("WHERE " + " AND ".join(filter_clauses))

    if sort:
        order_fragments = [f"{item.field} {item.dir.upper()}" for item in sort]
        sql_lines.append("ORDER BY " + ", ".join(order_fragments))

    return "\n".join(sql_lines)


def _log_api_event(action: str, payload: Optional[Any]) -> None:
    try:
        serialized = _serialize_payload(payload)
    except Exception as exc:  # pragma: no cover - logging safeguard
        logger.warning("failed to serialize payload for %s: %s", action, exc)
        serialized = "unserializable payload"
    logger.info("api_call", extra={"action": action, "payload": serialized})


def _serialize_payload(payload: Optional[Any]) -> Any:
    if payload is None:
        return None
    if hasattr(payload, "model_dump"):
        data = payload.model_dump()
    elif isinstance(payload, (dict, list, str, int, float, bool)):
        data = payload
    else:
        data = str(payload)
    encoded = jsonable_encoder(data)
    serialized = json.dumps(encoded, default=str)
    if len(serialized) > 2000:
        serialized = serialized[:2000] + "...<truncated>"
    return serialized


def _split_order_by_clause(sql: str) -> tuple[str, Optional[str]]:
    """Split off a top-level ORDER BY clause so we can wrap SQL in a derived table."""
    lower = sql.lower()
    depth = 0
    in_single = False
    in_double = False
    in_line_comment = False
    in_block_comment = False
    i = 0
    while i < len(sql):
        ch = sql[i]
        nxt = sql[i + 1] if i + 1 < len(sql) else ""

        if in_line_comment:
            if ch in "\r\n":
                in_line_comment = False
            i += 1
            continue
        if in_block_comment:
            if ch == "*" and nxt == "/":
                in_block_comment = False
                i += 2
                continue
            i += 1
            continue
        if ch == "-" and nxt == "-":
            in_line_comment = True
            i += 2
            continue
        if ch == "/" and nxt == "*":
            in_block_comment = True
            i += 2
            continue

        if ch == "'" and not in_double:
            in_single = not in_single
            i += 1
            continue
        if ch == '"' and not in_single:
            in_double = not in_double
            i += 1
            continue
        if in_single or in_double:
            i += 1
            continue
        if ch == "(":
            depth += 1
            i += 1
            continue
        if ch == ")":
            depth = max(depth - 1, 0)
            i += 1
            continue
        if depth == 0 and lower.startswith("order by", i):
            clause = sql[i + len("order by") :].strip()
            body = sql[:i].rstrip()
            return body, clause
        i += 1
    return sql, None


def _summarize_error(exc: Exception) -> str:
    """Return a short, user-friendly error summary."""
    detail = str(exc).strip()
    if not detail:
        return ""
    return detail.splitlines()[0][:200]
