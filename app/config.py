"""Application configuration powered by environment variables."""
from __future__ import annotations

from functools import lru_cache

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()


class Settings(BaseSettings):
    """Central application settings backed by environment variables."""

    api_key: str = Field(default="", alias="API_KEY")
    sql_conn_str: str = Field(default="", alias="SQLSERVER_CONN_STR")
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


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached Settings instance."""
    return Settings()
