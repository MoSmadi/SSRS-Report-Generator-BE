"""Application configuration powered by environment variables."""
from __future__ import annotations

from functools import lru_cache
from typing import Any, Dict, Tuple

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()


class Settings(BaseSettings):
    """Central application settings backed by environment variables."""

    sql_conn_str: str = Field(default="", alias="SQLSERVER_CONN_STR")
    sql_server_host: str = Field(default="", alias="SQLSERVER_HOST")
    sql_server_database: str = Field(default="", alias="SQLSERVER_DATABASE")
    sql_server_user: str = Field(default="", alias="SQLSERVER_USER")
    sql_server_password: str = Field(default="", alias="SQLSERVER_PASSWORD")
    sql_server_port: int = Field(default=1433, alias="SQLSERVER_PORT")
    sql_encrypt: bool = Field(default=True, alias="SQLSERVER_ENCRYPT")
    sql_trust_server_certificate: bool = Field(default=True, alias="SQLSERVER_TRUST_CERT")
    azure_openai_endpoint: str = Field(default="", alias="AZURE_OPENAI_ENDPOINT")
    azure_openai_deployment: str = Field(default="", alias="AZURE_OPENAI_DEPLOYMENT")
    azure_openai_api_key: str = Field(default="", alias="AZURE_OPENAI_API_KEY")
    ssrs_soap_wsdl: str = Field(
        default="http://your-ssrs/ReportServer/ReportService2010.asmx?wsdl",
        alias="SSRS_SOAP_WSDL",
    )
    report_folder: str = Field(default="/AutoReports", alias="SSRS_REPORT_FOLDER")
    shared_ds_path: str = Field(default="/_Shared/MainDS", alias="SHARED_DS_PATH")
    render_base: str = Field(default="http://your-ssrs/ReportServer", alias="SSRS_RENDER_BASE")
    server_host: str = Field(default="0.0.0.0", alias="SERVER_HOST")
    server_port: int = Field(default=8000, alias="SERVER_PORT")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    model_config = SettingsConfigDict(populate_by_name=True, extra="ignore")

    def model_post_init(self, __context: Any) -> None:
        """Normalize SQL Server settings using either discrete fields or a connection string."""
        if self.sql_conn_str:
            parsed = _parse_sql_connection_string(self.sql_conn_str)
            self._apply_parsed_sql_settings(parsed)

    def _apply_parsed_sql_settings(self, parsed: Dict[str, str]) -> None:
        server_value = parsed.get("server") or parsed.get("data source") or parsed.get("address")
        if server_value:
            host, port = _split_host_port(server_value)
            if not self.sql_server_host and host:
                self.sql_server_host = host
            if port and (not self.sql_server_port or self.sql_server_port == 1433):
                self.sql_server_port = port
        if not self.sql_server_database:
            self.sql_server_database = (
                parsed.get("database") or parsed.get("initial catalog") or self.sql_server_database
            )
        if not self.sql_server_user:
            for key in ("uid", "user id", "user", "username"):
                if key in parsed:
                    self.sql_server_user = parsed[key]
                    break
        if not self.sql_server_password:
            pwd = parsed.get("pwd") or parsed.get("password")
            if pwd:
                self.sql_server_password = pwd
        port_value = parsed.get("port")
        if port_value and (not self.sql_server_port or self.sql_server_port == 1433):
            try:
                self.sql_server_port = int(port_value)
            except ValueError:
                pass
        encrypt = parsed.get("encrypt")
        if encrypt is not None:
            self.sql_encrypt = _parse_bool(encrypt, default=self.sql_encrypt)
        trust = parsed.get("trustservercertificate") or parsed.get("trust server certificate")
        if trust is not None:
            self.sql_trust_server_certificate = _parse_bool(trust, default=self.sql_trust_server_certificate)

    @property
    def has_sql_credentials(self) -> bool:
        return bool(
            self.sql_server_host
            and self.sql_server_database
            and self.sql_server_user
            and self.sql_server_password
        )

    @property
    def resolved_sql_conn_str(self) -> str:
        """Return the connection string derived from env or provided directly."""
        if self.sql_conn_str:
            return self.sql_conn_str
        if not self.has_sql_credentials:
            return ""
        server = self.sql_server_host
        if self.sql_server_port:
            server = f"{server},{self.sql_server_port}"
        encrypt = "yes" if self.sql_encrypt else "no"
        trust = "yes" if self.sql_trust_server_certificate else "no"
        return (
            "Driver={ODBC Driver 18 for SQL Server};"
            f"Server={server};"
            f"Database={self.sql_server_database};"
            f"Uid={self.sql_server_user};"
            f"Pwd={self.sql_server_password};"
            f"Encrypt={encrypt};"
            f"TrustServerCertificate={trust};"
        )


def _parse_sql_connection_string(conn_str: str) -> Dict[str, str]:
    parsed: Dict[str, str] = {}
    for part in conn_str.split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        key, _, value = part.partition("=")
        parsed[key.strip().lower()] = value.strip().strip("'\"")
    return parsed


def _split_host_port(server_value: str) -> Tuple[str, int | None]:
    value = server_value.strip()
    if value.lower().startswith("tcp:"):
        value = value[4:]
    port: int | None = None
    if "," in value:
        host_part, port_part = value.split(",", 1)
        value = host_part.strip()
        port_part = port_part.strip()
        try:
            port = int(port_part)
        except ValueError:
            port = None
    return value, port


def _parse_bool(value: str | bool, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    return default


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached Settings instance."""
    return Settings()
