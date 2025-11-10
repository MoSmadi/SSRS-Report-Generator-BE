"""SQL Server connection utilities for SSRS RDL generation."""
import os
from typing import Optional
import pyodbc
from .config import get_settings


def get_connection_string(db_name: str) -> str:
    """
    Build a pyodbc connection string using stored credentials and the specified database.
    
    Args:
        db_name: Database name to connect to
        
    Returns:
        Connection string for pyodbc
    """
    settings = get_settings()
    
    # Build connection string from environment variables
    server = settings.sql_server_host
    port = settings.sql_server_port
    username = settings.sql_server_user
    password = settings.sql_server_password
    
    # Driver - use ODBC Driver 18 or 17 for SQL Server
    driver = os.getenv("SQLSERVER_DRIVER", "ODBC Driver 18 for SQL Server")
    
    # Build connection string
    conn_str = (
        f"DRIVER={{{driver}}};"
        f"SERVER={server},{port};"
        f"DATABASE={db_name};"
        f"UID={username};"
        f"PWD={password};"
        f"TrustServerCertificate=yes;"
        f"Encrypt=no"
    )
    
    return conn_str


def open_connection(db_name: str) -> pyodbc.Connection:
    """
    Open a connection to the specified database.
    
    Args:
        db_name: Database name to connect to
        
    Returns:
        pyodbc Connection object
    """
    conn_str = get_connection_string(db_name)
    return pyodbc.connect(conn_str, timeout=10)
