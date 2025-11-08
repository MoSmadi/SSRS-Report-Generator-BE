import os

from app import config

os.environ.setdefault("SQLSERVER_CONN_STR", "")
os.environ.setdefault("SQLSERVER_HOST", "")
os.environ.setdefault("SQLSERVER_DATABASE", "")
os.environ.setdefault("SQLSERVER_USER", "")
os.environ.setdefault("SQLSERVER_PASSWORD", "")
config.get_settings.cache_clear()

from app.main import app  # noqa: E402

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.mark.asyncio
async def test_generate_sql_contract(monkeypatch):
    meta = [
        {
            "name": "dbo.FactSales.OrderDate",
            "system_type_name": "datetime",
            "rdlType": "DateTime",
        },
        {
            "name": "dbo.FactSales.SalesAmount",
            "system_type_name": "money",
            "rdlType": "Float",
        },
    ]

    monkeypatch.setattr("app.routers.report.catalog.validate_shape", lambda sql: meta)
    monkeypatch.setattr(
        "app.routers.report.catalog.sample_values", lambda db, col, limit=5: ["Sample"]
    )

    payload = {
        "db": "DemoDW",
        "mapping": [
            {"term": "Sales", "column": "dbo.FactSales.SalesAmount", "role": "measure"},
            {
                "term": "OrderDate",
                "column": "dbo.FactSales.OrderDate",
                "role": "time",
                "grain": "month",
            },
        ],
        "spec": {
            "metrics": ["Sales"],
            "dimensions": ["Region"],
            "filters": [],
            "sort": [{"field": "Sales", "dir": "desc"}],
            "grain": "month",
        },
    }

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/report/generateSQL", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "SELECT" in data["sql"]
    assert data["params"] == []
    assert len(data["columns"]) == 2
    first = data["columns"][0]
    assert first["samples"] == ["Sample"]
    assert first["rdlType"] == "DateTime"


@pytest.mark.asyncio
async def test_publish_report_contract(monkeypatch):
    monkeypatch.setattr(
        "app.routers.report.upload_rdl",
        lambda folder, name, rdl: {"path": f"{folder}/{name}", "id": "abc"},
    )
    monkeypatch.setattr("app.routers.report.set_shared_datasource", lambda *args, **kwargs: None)
    monkeypatch.setattr("app.routers.report.set_report_datasources", lambda *args, **kwargs: True)
    monkeypatch.setattr("app.routers.report.get_system_info", lambda: {"version": "test"})

    payload = {
        "db": {"name": "DemoDW"},
        "report": {
            "title": "Monthly Sales",
            "folder": "/AutoReports",
            "shared_data_source_path": "/_Shared/MainDS",
        },
        "mapping": [
            {"term": "Sales", "column": "dbo.FactSales.SalesAmount", "role": "measure"},
        ],
        "columns": [
            {
                "name": "OrderDate",
                "source": "dbo.FactSales.OrderDate",
                "system_type_name": "datetime",
                "rdlType": "DateTime",
                "role": "time",
                "display_name": "Order Date",
                "description": None,
                "include": True,
                "agg": None,
                "format": "None",
                "samples": ["2024-01-01"],
                "null_pct": 0.0,
            },
            {
                "name": "SalesAmount",
                "source": "dbo.FactSales.SalesAmount",
                "system_type_name": "money",
                "rdlType": "Float",
                "role": "measure",
                "display_name": "Sales Amount",
                "description": None,
                "include": True,
                "agg": "SUM",
                "format": "Currency",
                "samples": ["100"],
                "null_pct": 0.0,
            },
        ],
        "parameters": [
            {"name": "StartDate", "rdlType": "DateTime", "default": "2024-01-01"},
            {"name": "EndDate", "rdlType": "DateTime", "default": "2024-12-31"},
        ],
        "filters": [
            {"field": "dbo.FactSales.OrderDate", "op": ">=", "param": "StartDate"},
            {"field": "dbo.FactSales.OrderDate", "op": "<=", "param": "EndDate"},
        ],
        "sort": [{"field": "SalesAmount", "dir": "desc"}],
        "chart": {
            "type": "line",
            "category": "OrderDate",
            "series": ["Sales"],
            "values": ["SalesAmount"],
        },
    }

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/report/publishReport", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["path"] == "/AutoReports/Monthly Sales"
    assert data["render_url_pdf"].startswith("http://your-ssrs/ReportServer?")
    assert data["server"] == {"version": "test"}
    assert len(data["dataset_fields"]) == 2
    assert data["echo"]["report"]["title"] == "Monthly Sales"
