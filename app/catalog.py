"""SQL Server metadata catalog helpers."""
from __future__ import annotations

import contextlib
from typing import Any

try:  # pragma: no cover - executed in production
    import pyodbc
except ImportError:  # pragma: no cover - optional for tests
    pyodbc = None

from .config import get_settings

_SETTINGS = get_settings()


def _conn(database: str | None = None):
    if pyodbc is None:
        raise RuntimeError("pyodbc is not installed")
    conn_str = _SETTINGS.sql_conn_str
    if database:
        conn_str += f";DATABASE={database}"
    return pyodbc.connect(conn_str, timeout=5)


def list_databases() -> list[dict[str, str]]:
    if not _SETTINGS.sql_conn_str:
        return [{"name": "DemoDW"}]
    with contextlib.closing(_conn()) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sys.databases WHERE database_id > 4")
        return [{"name": row[0]} for row in cursor.fetchall()]


def list_columns(db: str) -> list[dict[str, Any]]:
    if not _SETTINGS.sql_conn_str:
        return [
            {"name": "dbo.FactSales.OrderDate", "type": "datetime", "rdlType": "DateTime"},
            {"name": "dbo.FactSales.Region", "type": "varchar", "rdlType": "String"},
            {"name": "dbo.FactSales.SalesAmount", "type": "decimal", "rdlType": "Float"},
        ]
    query = (
        "SELECT TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME, DATA_TYPE "
        "FROM INFORMATION_SCHEMA.COLUMNS ORDER BY TABLE_SCHEMA, TABLE_NAME"
    )
    with contextlib.closing(_conn(db)) as conn:
        cursor = conn.cursor()
        cursor.execute(query)
        result = []
        for schema, table, column, data_type in cursor.fetchall():
            fq = f"{schema}.{table}.{column}"
            result.append({"name": fq, "type": data_type, "rdlType": map_sql_type_to_rdl(data_type)})
        return result


def validate_shape(sql_text: str) -> list[dict[str, Any]]:
    if not _SETTINGS.sql_conn_str:
        return [
            {"name": "OrderDate", "system_type_name": "datetime", "rdlType": "DateTime"},
            {"name": "Region", "system_type_name": "nvarchar", "rdlType": "String"},
            {"name": "SalesAmount", "system_type_name": "money", "rdlType": "Float"},
        ]
    query = "EXEC sp_describe_first_result_set @tsql = ?"
    with contextlib.closing(_conn()) as conn:
        cursor = conn.cursor()
        cursor.execute(query, sql_text)
        columns = []
        for row in cursor.fetchall():
            if not row.name:
                continue
            columns.append(
                {
                    "name": row.name,
                    "system_type_name": row.system_type_name,
                    "rdlType": map_sql_type_to_rdl(row.system_type_name),
                }
            )
        return columns


def sample_values(db: str, column: str, limit: int = 5) -> list[str]:
    if not _SETTINGS.sql_conn_str:
        return ["North", "South"] if "Region" in column else ["1000", "2000"]
    schema_table, col = column.rsplit(".", 1)
    schema, table = schema_table.split(".")
    query = f"SELECT TOP {limit} [{col}] FROM {schema}.{table} WHERE [{col}] IS NOT NULL"
    with contextlib.closing(_conn(db)) as conn:
        cursor = conn.cursor()
        cursor.execute(query)
        return [str(row[0]) for row in cursor.fetchall()]


def map_sql_type_to_rdl(sql_type: str | None) -> str:
    if not sql_type:
        return "String"
    sql_type = sql_type.lower()
    if any(t in sql_type for t in ("char", "text", "xml")):
        return "String"
    if any(t in sql_type for t in ("date", "time")):
        return "DateTime"
    if any(t in sql_type for t in ("int", "numeric", "decimal", "money", "float", "real")):
        return "Float"
    if "bit" in sql_type:
        return "Boolean"
    return "String"
