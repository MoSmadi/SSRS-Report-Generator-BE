"""SQL Server metadata catalog helpers."""
from __future__ import annotations

import contextlib
from typing import Any, List, Optional

from .db import open_sql_connection, sql_connection_available
from .schemas import ColumnMetadata

NUMERIC_TYPES = {"int", "bigint", "smallint", "tinyint", "decimal", "numeric", "money", "float", "real", "smallmoney"}
DATE_TYPES = {"date", "datetime", "datetime2", "smalldatetime", "time", "datetimeoffset"}


def _conn(database: Optional[str] = None):
    return open_sql_connection(database or None)


def list_databases() -> list[dict[str, str]]:
    if not sql_connection_available():
        return [{"name": "DemoDW"}]
    with contextlib.closing(_conn()) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sys.databases WHERE database_id > 4")
        return [{"name": row[0]} for row in cursor.fetchall()]


def list_columns(db: str) -> List[ColumnMetadata]:
    if not sql_connection_available():
        return _demo_columns()
    query = (
        "SELECT TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME, DATA_TYPE "
        "FROM INFORMATION_SCHEMA.COLUMNS ORDER BY TABLE_SCHEMA, TABLE_NAME, ORDINAL_POSITION"
    )
    columns: List[ColumnMetadata] = []
    with contextlib.closing(_conn(db)) as conn:
        cursor = conn.cursor()
        cursor.execute(query)
        for schema, table, column, data_type in cursor.fetchall():
            qualified = f"{schema}.{table}.{column}"
            bracketed = f"[{schema}].[{table}].[{column}]"
            columns.append(
                ColumnMetadata(
                    schema=schema,
                    table=table,
                    column=column,
                    dataType=data_type,
                    isNumeric=_is_numeric_type(data_type),
                    isDateLike=_is_date_type(data_type),
                    sampleValues=None,
                    name=qualified,
                    bracketedName=bracketed,
                )
            )
    return columns


def validate_shape(sql_text: str) -> list[dict[str, Any]]:
    if not sql_connection_available():
        return [
            {"name": "OrderDate", "system_type_name": "datetime", "rdlType": "DateTime"},
            {"name": "Region", "system_type_name": "nvarchar", "rdlType": "String"},
            {"name": "SalesAmount", "system_type_name": "money", "rdlType": "Float"},
        ]
    query = "EXEC sp_describe_first_result_set @tsql = ?"
    with contextlib.closing(_conn()) as conn:
        cursor = conn.cursor()
        cursor.execute(query, sql_text)
        rows = cursor.fetchall()
    columns = []
    for row in rows:
        name = _get_tuple_value(row, 2)  # column name
        if not name:
            continue
        system_type = _get_tuple_value(row, 5)  # system_type_name
        columns.append(
            {
                "name": name,
                "system_type_name": system_type,
                "rdlType": map_sql_type_to_rdl(system_type),
            }
        )
    return columns


def sample_values(db: str, column: str, limit: int = 5) -> list[str]:
    if not sql_connection_available():
        return ["North", "South"] if "Region" in column else ["1000", "2000"]
    schema_table, col = column.rsplit(".", 1)
    schema, table = schema_table.split(".")
    query = f"SELECT TOP {limit} [{col}] FROM {schema}.{table} WHERE [{col}] IS NOT NULL"
    with contextlib.closing(_conn(db)) as conn:
        cursor = conn.cursor()
        cursor.execute(query)
        return [str(row[0]) for row in cursor.fetchall()]


def map_sql_type_to_rdl(sql_type: Optional[str]) -> str:
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


def _get_tuple_value(row: Any, index: int) -> Optional[str]:
    if isinstance(row, dict):
        # Safety: handle environments that still return dicts
        return row.get("name") if index == 2 else row.get("system_type_name")
    if isinstance(row, (list, tuple)) and len(row) > index:
        value = row[index]
        return value if value is not None else None
    return None


def _is_numeric_type(data_type: str) -> bool:
    return data_type.lower() in NUMERIC_TYPES


def _is_date_type(data_type: str) -> bool:
    return data_type.lower() in DATE_TYPES


def _demo_columns() -> List[ColumnMetadata]:
    return [
        ColumnMetadata(
            schema="dbo",
            table="FactSales",
            column="OrderDate",
            dataType="datetime",
            isNumeric=False,
            isDateLike=True,
            sampleValues=["2024-01-01", "2024-01-02"],
            name="dbo.FactSales.OrderDate",
            bracketedName="[dbo].[FactSales].[OrderDate]",
        ),
        ColumnMetadata(
            schema="dbo",
            table="FactSales",
            column="Region",
            dataType="nvarchar",
            isNumeric=False,
            isDateLike=False,
            sampleValues=["West", "South"],
            name="dbo.FactSales.Region",
            bracketedName="[dbo].[FactSales].[Region]",
        ),
        ColumnMetadata(
            schema="dbo",
            table="FactSales",
            column="SalesAmount",
            dataType="money",
            isNumeric=True,
            isDateLike=False,
            sampleValues=["1000", "2500"],
            name="dbo.FactSales.SalesAmount",
            bracketedName="[dbo].[FactSales].[SalesAmount]",
        ),
    ]


def demo_columns() -> List[ColumnMetadata]:
    """Return static demo columns used when SQL Server is unavailable."""
    return _demo_columns()
