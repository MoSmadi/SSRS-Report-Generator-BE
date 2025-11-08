"""Shared SQL Server connection helpers."""
from __future__ import annotations

from typing import Optional

from .config import get_settings

try:  # pragma: no cover - optional dependency during import
    import pyodbc
except ImportError:  # pragma: no cover - ensures informative error later
    pyodbc = None


def sql_connection_available() -> bool:
    """Return True when a usable SQL Server connection string is configured."""
    return bool(get_settings().resolved_sql_conn_str)


def open_sql_connection(database: Optional[str] = None):
    """Open a SQL Server connection using pyodbc."""
    settings = get_settings()
    conn_str = settings.resolved_sql_conn_str
    if not conn_str:
        raise RuntimeError("SQL Server environment variables are incomplete")
    if pyodbc is None:
        raise RuntimeError("pyodbc is not installed; run `pip install pyodbc`.")
    effective_conn_str = _override_database(conn_str, database) if database else conn_str
    return pyodbc.connect(effective_conn_str, timeout=30)


def _override_database(conn_str: str, database: Optional[str]) -> str:
    if not database:
        return conn_str
    parts = [part for part in conn_str.strip().rstrip(";").split(";") if part]
    updated: list[str] = []
    replaced = False
    for part in parts:
        lowered = part.lower()
        if lowered.startswith("database=") or lowered.startswith("initial catalog="):
            updated.append(f"Database={database}")
            replaced = True
        else:
            updated.append(part)
    if not replaced:
        updated.append(f"Database={database}")
    return ";".join(updated) + ";"
