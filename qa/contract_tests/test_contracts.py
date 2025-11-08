from __future__ import annotations

from typing import Any

import pytest
import requests

from .conftest import ApiClient, require_success


def is_mapping(item: dict[str, Any]) -> bool:
    term_ok = isinstance(item.get("term"), str)
    role_ok = item.get("role") in {"metric", "dimension", "measure", "time"}
    column_val = item.get("column")
    column_ok = column_val is None or isinstance(column_val, str)
    return term_ok and role_ok and column_ok


def is_column_def(item: dict[str, Any]) -> bool:
    return isinstance(item.get("name"), str) and isinstance(item.get("rdlType"), str)


def is_param(item: dict[str, Any]) -> bool:
    return isinstance(item.get("name"), str)


def normalize_mapping(data: list[dict[str, Any]], columns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    col_names = {col.get("name") or col.get("column"): col for col in columns}
    results: list[dict[str, Any]] = []
    for item in data:
        column = item.get("column") or item.get("source")
        if not column or column not in col_names:
            continue
        results.append(item)
    return results


@pytest.fixture(scope="session")
def infer_result(api: ApiClient, first_database: str) -> dict[str, Any]:
    payload = {
        "db": first_database,
        "title": "Contract Report",
        "text": "total sales by month and region",
    }
    response, data = api.post_json("/report/inferFromNaturalLanguage", json=payload)
    data = require_success(response, data, "inferFromNaturalLanguage")
    assert isinstance(data.get("spec"), dict)
    assert isinstance(data.get("suggestedMapping"), list)
    assert isinstance(data.get("availableColumns"), list)
    assert isinstance(data.get("schemaInsights"), dict)
    mapping = normalize_mapping(data["suggestedMapping"], data["availableColumns"])
    if not mapping:
        pytest.skip("Unable to derive mapping from infer output; adjust test prompt.")
    data["db"] = first_database
    data["mapping"] = mapping
    return data


@pytest.fixture(scope="session")
def generate_result(api: ApiClient, infer_result: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "db": infer_result["db"],
        "mapping": infer_result["mapping"],
        "spec": infer_result["spec"],
    }
    response, data = api.post_json("/report/generateSQL", json=payload)
    data = require_success(response, data, "generateSQL")
    assert isinstance(data.get("sql"), str) and data["sql"].strip()
    assert isinstance(data.get("columns"), list) and data["columns"]
    data["db"] = infer_result["db"]
    data["mapping"] = infer_result["mapping"]
    data["spec"] = infer_result["spec"]
    return data


def test_customer_databases_shape(api: ApiClient):
    response = api.request("GET", "/report/customerDatabases")
    assert response.status_code == 200
    doc = response.json()
    assert "databases" in doc and isinstance(doc["databases"], list)
    if doc["databases"]:
        assert isinstance(doc["databases"][0].get("name"), str)


def test_infer_contract(infer_result: dict[str, Any]):
    assert isinstance(infer_result["spec"], dict)
    assert all(is_mapping(m) for m in infer_result["mapping"])


def test_generate_sql_contract(generate_result: dict[str, Any]):
    columns = generate_result["columns"]
    assert all(is_column_def(col) for col in columns)
    params = generate_result.get("params")
    assert isinstance(params, list)
    for param in params:
        assert is_param(param)


def test_preview_contract(api: ApiClient, generate_result: dict[str, Any]):
    payload = {
        "db": generate_result["db"],
        "sql": generate_result["sql"],
        "params": {param.get("name"): param.get("value") for param in generate_result.get("params", []) if param.get("name")},
        "limit": 5,
    }
    response, data = api.post_json("/report/preview", json=payload)
    data = require_success(response, data, "preview")
    assert isinstance(data.get("rows"), list)
    assert isinstance(data.get("row_count"), int)


def test_publish_contract(api: ApiClient, generate_result: dict[str, Any]):
    columns = generate_result["columns"]
    mapping = generate_result["mapping"]
    parameters = [
        {
            "name": param.get("name", "Param").lstrip("@"),
            "rdlType": param.get("rdlType", "String"),
            "default": param.get("value"),
        }
        for param in generate_result.get("params", [])
        if param.get("name")
    ]
    payload = {
        "db": {"name": generate_result["db"]},
        "report": {
            "title": "Contract Report",
            "folder": "/AutoReports",
            "shared_data_source_path": "/_Shared/MainDS",
        },
        "mapping": mapping,
        "columns": columns,
        "parameters": parameters,
        "filters": [
            {
                "field": columns[0].get("source") or columns[0].get("name"),
                "op": "=",
                "param": parameters[0]["name"] if parameters else "Param",
            }
        ],
        "sort": [{"field": columns[0].get("name"), "dir": "asc"}],
        "chart": None,
    }
    response, data = api.post_json("/report/publishReport", json=payload)
    if response.status_code == 200:
        assert "render_url_pdf" in data
        return
    error = data.get("error", {}).get("message", "")
    if response.status_code in {400, 502} and "ssrs" in error.lower():
        pytest.xfail(f"SSRS unavailable: {error}")
    pytest.fail(f"Unexpected publish response: {response.status_code} {data}")


def test_api_key_required(api: ApiClient):
    url = f"{api.base_url.rstrip('/')}/report/customerDatabases"
    response = requests.get(url, timeout=10)
    assert response.status_code == 401


def test_preview_invalid_limit(api: ApiClient, generate_result: dict[str, Any]):
    payload = {
        "db": generate_result["db"],
        "sql": generate_result["sql"],
        "params": {},
        "limit": 5000,
    }
    response, data = api.post_json("/report/preview", json=payload)
    assert response.status_code == 400, f"Expected 400, got {response.status_code}: {data}"


def test_publish_missing_datasource(api: ApiClient, generate_result: dict[str, Any]):
    payload = {
        "db": {"name": generate_result["db"]},
        "report": {"title": "Contract Report", "folder": "/AutoReports"},
        "mapping": generate_result["mapping"],
        "columns": generate_result["columns"],
        "parameters": [],
        "filters": [],
        "sort": [],
        "chart": None,
    }
    response, data = api.post_json("/report/publishReport", json=payload)
    assert response.status_code == 400, f"Expected 400, got {response.status_code}: {data}"
