"""Report-related API endpoints."""
from __future__ import annotations

import contextlib
import logging
from typing import Any

try:  # pragma: no cover - optional dependency
    import pyodbc
except ImportError:  # pragma: no cover
    pyodbc = None

from fastapi import APIRouter, Depends

from .. import catalog, intent, sqlgen
from ..config import get_settings
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
from ..utils.security import require_api_key

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter(prefix="/report", tags=["reports"], dependencies=[Depends(require_api_key)])


@router.get("/customerDatabases")
def list_databases() -> dict[str, list[dict[str, str]]]:
    try:
        databases = catalog.list_databases()
    except Exception as exc:  # pragma: no cover - requires DB
        logger.exception("failed to list databases")
        raise ServiceError("Unable to list databases", "catalog_error", status_code=502) from exc
    return {"databases": databases}


@router.post("/inferFromNaturalLanguage", response_model=InferOut)
def infer_from_nl(payload: InferIn) -> InferOut:
    return intent.infer_from_nl(payload.db, payload.title, payload.text)


@router.post("/generateSQL", response_model=GenSQLOut)
def generate_sql(payload: GenSQLIn) -> GenSQLOut:
    sql_text, params = sqlgen.build_sql(payload.spec, payload.mapping)
    try:
        columns_meta = catalog.validate_shape(sql_text)
    except Exception as exc:  # pragma: no cover - DB only
        logger.exception("failed to validate SQL shape")
        raise ServiceError("Unable to validate SQL output", "catalog_error", status_code=502) from exc

    column_defs: list[ColumnDef] = []
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

    return GenSQLOut(sql=sql_text, params=params, columns=column_defs)


@router.post("/preview", response_model=PreviewOut)
def preview(payload: PreviewIn) -> PreviewOut:
    limit = max(1, min(payload.limit, 200))
    rows: list[dict[str, Any]]
    if pyodbc is None or not settings.sql_conn_str:
        rows = [{"message": "Preview unavailable in this environment"}]
        return PreviewOut(rows=rows[:limit], row_count=len(rows))

    declares = []
    values: list[Any] = []
    for key, value in payload.params.items():
        declares.append(f"DECLARE {key} NVARCHAR(4000) = ?;")
        values.append(value)

    limited_sql = f"SELECT TOP {limit} * FROM (\n{payload.sql}\n) AS src"
    sql_text = "\n".join(declares + [limited_sql])

    try:
        with contextlib.closing(pyodbc.connect(settings.sql_conn_str, timeout=5)) as conn:
            cursor = conn.cursor()
            cursor.execute(sql_text, values)
            columns = [col[0] for col in cursor.description]
            rows = [dict(zip(columns, row)) for row in cursor.fetchmany(limit)]
    except pyodbc.Error as exc:  # pragma: no cover - DB specific
        logger.exception("preview execution failed")
        raise ServiceError("Preview query failed", "preview_error", status_code=502) from exc
    return PreviewOut(rows=rows, row_count=len(rows))


@router.post("/publishReport", response_model=PublishOut)
def publish_report(payload: PublishIn) -> PublishOut:
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

    return PublishOut(
        path=upload_result["path"],
        render_url_pdf=render_url,
        server=server_info,
        dataset_fields=[field.model_dump() for field in payload.columns],
        echo=payload.model_dump(),
    )


def _build_publish_sql(
    columns: list[ColumnDef],
    filters: list[FilterDef],
    sort: list[SortDef] | None,
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
