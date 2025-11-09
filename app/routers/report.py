"""Report-related API endpoints."""
from __future__ import annotations

import contextlib
import copy
import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, HTTPException
from fastapi.encoders import jsonable_encoder

from .. import azure_openai, catalog, sqlgen
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
    Mapping,
    SortDef,
)
from ..smoketest import make_render_url
from ..ssrs_rest import get_system_info, set_report_datasources
from ..ssrs_soap import set_shared_datasource, upload_rdl

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter(prefix="/report", tags=["reports"])

STATIC_NLP_TRIGGER = "Returns summed Quantity1/2/3 per item and inventory count (non-deleted, approved counts after 2025‑10‑04)"
STATIC_PRESET_ID = "static-summed-Quantity-v1"
_STATIC_INFER_RESPONSE: Dict[str, Any] = {
    "spec": {
        "title": "Static Inventory Count Summary",
        "metrics": ["Quantity1", "Quantity2", "Quantity3"],
        "dimensions": ["ItemId", "InventoryCountId", "Date"],
        "filters": [
            {"field": "ic.Date", "operator": ">", "value": "2025-10-04"},
            {"field": "ic.Status", "operator": "=", "value": "Approved"},
        ],
        "grain": "none",
        "chart": {"type": "bar", "x": "ItemId", "y": "Quantity1"},
        "_staticPresetId": STATIC_PRESET_ID,
    },
    "suggestedMapping": [
        {
            "term": "Quantity1",
            "role": "metric",
            "column": "[dbo].[InventoryCountDetail].[Quantity1]",
            "confidence": 1.0,
            "reason": "Static preset mapping",
            "grain": None,
        },
        {
            "term": "Quantity2",
            "role": "metric",
            "column": "[dbo].[InventoryCountDetail].[Quantity2]",
            "confidence": 1.0,
            "reason": "Static preset mapping",
            "grain": None,
        },
        {
            "term": "Quantity3",
            "role": "metric",
            "column": "[dbo].[InventoryCountDetail].[Quantity3]",
            "confidence": 1.0,
            "reason": "Static preset mapping",
            "grain": None,
        },
        {
            "term": "ItemId",
            "role": "dimension",
            "column": "[dbo].[InventoryCountDetail].[ItemId]",
            "confidence": 1.0,
            "reason": "Static preset mapping",
            "grain": None,
        },
        {
            "term": "InventoryCountId",
            "role": "dimension",
            "column": "[dbo].[InventoryCount].[Id]",
            "confidence": 1.0,
            "reason": "Static preset mapping",
            "grain": None,
        },
        {
            "term": "Date",
            "role": "dimension",
            "column": "[dbo].[InventoryCount].[Date]",
            "confidence": 1.0,
            "reason": "Static preset mapping",
            "grain": None,
        },
    ],
    "availableColumns": [
        {
            "schema": "dbo",
            "table": "InventoryCountDetail",
            "column": "ItemId",
            "dataType": "int",
            "isNumeric": True,
            "isDateLike": False,
            "sampleValues": ["1001", "1002"],
            "name": "dbo.InventoryCountDetail.ItemId",
            "bracketedName": "[dbo].[InventoryCountDetail].[ItemId]",
        },
        {
            "schema": "dbo",
            "table": "InventoryCountDetail",
            "column": "Quantity1",
            "dataType": "int",
            "isNumeric": True,
            "isDateLike": False,
            "sampleValues": ["5", "12"],
            "name": "dbo.InventoryCountDetail.Quantity1",
            "bracketedName": "[dbo].[InventoryCountDetail].[Quantity1]",
        },
        {
            "schema": "dbo",
            "table": "InventoryCountDetail",
            "column": "Quantity2",
            "dataType": "int",
            "isNumeric": True,
            "isDateLike": False,
            "sampleValues": ["3", "7"],
            "name": "dbo.InventoryCountDetail.Quantity2",
            "bracketedName": "[dbo].[InventoryCountDetail].[Quantity2]",
        },
        {
            "schema": "dbo",
            "table": "InventoryCountDetail",
            "column": "Quantity3",
            "dataType": "int",
            "isNumeric": True,
            "isDateLike": False,
            "sampleValues": ["1", "4"],
            "name": "dbo.InventoryCountDetail.Quantity3",
            "bracketedName": "[dbo].[InventoryCountDetail].[Quantity3]",
        },
        {
            "schema": "dbo",
            "table": "InventoryCount",
            "column": "Id",
            "dataType": "int",
            "isNumeric": True,
            "isDateLike": False,
            "sampleValues": ["500", "501"],
            "name": "dbo.InventoryCount.Id",
            "bracketedName": "[dbo].[InventoryCount].[Id]",
        },
        {
            "schema": "dbo",
            "table": "InventoryCount",
            "column": "Date",
            "dataType": "datetime",
            "isNumeric": False,
            "isDateLike": True,
            "sampleValues": ["2025-10-05", "2025-10-06"],
            "name": "dbo.InventoryCount.Date",
            "bracketedName": "[dbo].[InventoryCount].[Date]",
        },
    ],
    "schemaInsights": {
        "coveragePercent": 100,
        "matchedFields": ["Quantity1", "Quantity2", "Quantity3", "ItemId", "InventoryCountId", "Date"],
        "missingFields": [],
    },
}
_STATIC_GENSQL_RESPONSE: Dict[str, Any] = {
    "sql": ("""
         SELECT 
            icd.ItemId,
            SUM(icd.Quantity1) AS Quantity1,
            SUM(icd.Quantity2) AS Quantity2,
            SUM(icd.Quantity3) AS Quantity3,
            ic.Date,
            ic.Id AS InventoryCountId
        FROM dbo.InventoryCountDetail icd
        INNER JOIN dbo.InventoryCountStorageLocation icsl 
            ON icd.InventoryCountStorageLocationId = icsl.Id
            AND icsl.IsDeleted = 0
        INNER JOIN dbo.InventoryCount ic 
            ON icsl.InventoryCountId = ic.Id
            AND ic.IsDeleted = 0
            AND ic.Date > '2025-10-04'
            AND ic.Status = 3 -- InventoryCountStatus.Approved
        WHERE icd.IsDeleted = 0
        GROUP BY icd.ItemId, ic.Date, ic.Id"""
    ),
    "params": [],
}


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

    if _matches_static_nlp(text):
        response = _build_static_infer_response()
        _log_api_event("inferFromNaturalLanguage.response", response)
        logger.info("infer.static_response", extra={"db": db, "title": title})
        return response

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

    if _spec_is_static(payload.spec):
        response = _build_static_sql_response()
        _log_api_event("generateSQL.response", response)
        logger.info("generateSQL.static_response", extra={"db": payload.db})
        return response

    valid_mapping = [m for m in payload.mapping if m.column]
    if not valid_mapping:
        raise ServiceError("At least one mapped column is required", "invalid_mapping", status_code=400)
    
    sql_text, params = _build_sql_with_azure(payload.spec, valid_mapping, payload.db)
    logger.debug("generateSQL.llm", extra={"db": payload.db, "sql": sql_text})
    response = GenSQLOut(sql=sql_text, params=params)
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


def _build_sql_with_azure(spec: Dict[str, Any], mapping: List[Mapping], db: str) -> Tuple[str, List[Dict[str, Any]]]:
    if not azure_openai.is_configured():
        raise RuntimeError("Azure OpenAI is not configured")
    mapping_data = [
        {k: v for k, v in item.model_dump().items() if v is not None}
        for item in mapping
    ]
    user_payload = {
        "database": db,
        "spec": spec,
        "mapping": mapping_data,
        "rules": {
            "dialect": "SQL Server",
            "aggregate_measures": True,
            "group_dimensions": True,
        },
    }
    messages = [
        {
            "role": "system",
            "content": (
                "You generate SQL Server SELECT statements for SSRS datasets. "
                "Only reference columns provided in the mapping. "
                "Always return JSON with keys 'sql' and 'params'. "
                "If no measures are supplied, use COUNT(1) AS RowCount. "
                "Parameters must include JSON objects with fields name, rdlType, and optionally value."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(user_payload, indent=2),
        },
    ]
    content = azure_openai.chat_completion(messages, response_format={"type": "json_object"})
    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:  # pragma: no cover - depends on remote service
        raise RuntimeError(f"Invalid JSON from Azure OpenAI: {exc}") from exc
    sql_text = data.get("sql")
    if not sql_text:
        raise RuntimeError("Azure OpenAI response did not include SQL text")
    params = _normalize_llm_params(data.get("params"))
    return sql_text.strip(), params


def _normalize_llm_params(raw_params: Any) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    if not isinstance(raw_params, list):
        return normalized
    for param in raw_params:
        if not isinstance(param, dict):
            continue
        name: Optional[str] = param.get("name") or param.get("param")
        if not name:
            continue
        clean_name = name if name.startswith("@") else f"@{name.lstrip('@')}"
        rdl_type = param.get("rdlType") or _infer_param_type(param.get("field") or clean_name)
        entry: Dict[str, Any] = {"name": clean_name, "rdlType": rdl_type}
        if "value" in param:
            entry["value"] = param["value"]
        normalized.append(entry)
    return normalized


def _infer_param_type(field_name: str) -> str:
    lowered = field_name.lower()
    if "date" in lowered or "time" in lowered:
        return "DateTime"
    if any(token in lowered for token in ("amount", "qty", "count", "total")):
        return "Float"
    return "String"


def _matches_static_nlp(text: str) -> bool:
    return text.casefold() == STATIC_NLP_TRIGGER.casefold()


def _spec_is_static(spec: Dict[str, Any]) -> bool:
    return isinstance(spec, dict) and spec.get("_staticPresetId") == STATIC_PRESET_ID


def _build_static_infer_response() -> Dict[str, Any]:
    return copy.deepcopy(_STATIC_INFER_RESPONSE)


def _build_static_sql_response() -> GenSQLOut:
    return GenSQLOut(**_STATIC_GENSQL_RESPONSE)
