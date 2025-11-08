"""Imperative smoke test suite for the FastAPI backend."""
from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass
from typing import Any, Callable

import requests

DEFAULT_ENV = {
    "API_BASE": "http://localhost:8000",
    "TEST_REPORT_TITLE": "Sales by Month and Region 2024",
    "TEST_PROMPT": "total sales by month and region for 2024, line chart, filter region in (West, South)",
    "TEST_FOLDER": "/AutoReports",
    "TEST_SHARED_DS_PATH": "/_Shared/MainDS",
    "TEST_PREVIEW_LIMIT": "10",
}

TIMEOUT = 10


def env(key: str) -> str:
    value = os.getenv(key)
    return value if value not in (None, "") else DEFAULT_ENV[key]


@dataclass
class StepResult:
    name: str
    success: bool
    message: str
    duration: float


class SmokeContext:
    def __init__(self) -> None:
        self.api_base = env("API_BASE").rstrip("/")
        self.headers = {"Content-Type": "application/json"}
        self.db_name: str | None = None
        self.spec: dict[str, Any] | None = None
        self.mapping: list[dict[str, Any]] = []
        self.columns: list[dict[str, Any]] = []
        self.params: list[dict[str, Any]] = []
        self.sql_text: str | None = None
        self.publish_payload: dict[str, Any] | None = None
        self.summaries: list[StepResult] = []
        self.ssrs_warning: str | None = None

    def request(self, method: str, path: str, **kwargs: Any) -> requests.Response:
        url = f"{self.api_base}{path}"
        headers = kwargs.pop("headers", {})
        headers = {**self.headers, **headers}
        return requests.request(method, url, headers=headers, timeout=TIMEOUT, **kwargs)

    def record(self, name: str, func: Callable[[], None]) -> None:
        start = time.time()
        try:
            func()
            success = True
            message = "ok"
        except SoftFailure as exc:
            success = False
            message = str(exc)
            self.summaries.append(StepResult(name, success, message, time.time() - start))
            self._exit_with_summary(code=2)
        except SsrsUnavailable as exc:
            success = True
            message = str(exc)
            self.ssrs_warning = message
        except Exception as exc:  # pragma: no cover - CLI path
            success = False
            message = f"{exc}"
            self.summaries.append(StepResult(name, success, message, time.time() - start))
            self._exit_with_summary(code=1, extra_message=f"{name} failed: {exc}")
        duration = time.time() - start
        self.summaries.append(StepResult(name, success, message, duration))

    def _exit_with_summary(self, code: int, extra_message: str | None = None) -> None:
        print_summary(self.summaries, self.ssrs_warning)
        if extra_message:
            print(extra_message, file=sys.stderr)
        sys.exit(code)


class SoftFailure(RuntimeError):
    """Raised when the smoke test should exit with warning (code 2)."""


class SsrsUnavailable(RuntimeError):
    """Raised when SSRS publish fails but should not fail the smoke overall."""


def ensure_json(response: requests.Response) -> dict[str, Any]:
    try:
        return response.json()
    except ValueError as exc:  # pragma: no cover - network only
        raise RuntimeError(f"Non-JSON response: {response.status_code} {response.text}") from exc


def step_customer_databases(ctx: SmokeContext) -> None:
    for attempt in (1, 2):
        resp = ctx.request("GET", "/report/customerDatabases")
        if resp.status_code == 200:
            data = ensure_json(resp)
            databases = data.get("databases") or []
            if not databases:
                raise RuntimeError("No databases returned from /report/customerDatabases")
            ctx.db_name = databases[0]["name"]
            return
        time.sleep(1 if attempt == 1 else 0)
    raise RuntimeError(f"Failed to list databases: {resp.status_code} {resp.text}")


def step_infer(ctx: SmokeContext) -> None:
    assert ctx.db_name, "Database must be set before inferring"
    payload = {
        "db": ctx.db_name,
        "title": env("TEST_REPORT_TITLE"),
        "text": env("TEST_PROMPT"),
    }
    resp = ctx.request("POST", "/report/inferFromNaturalLanguage", json=payload)
    if resp.status_code != 200:
        raise RuntimeError(f"Infer failed: {resp.status_code} {resp.text}")
    data = ensure_json(resp)
    required_keys = {"spec", "suggestedMapping", "availableColumns", "schemaInsights"}
    if not required_keys.issubset(data.keys()):
        raise RuntimeError(f"Infer response missing keys: {data.keys()}")
    ctx.spec = data["spec"]
    ctx.mapping = normalize_mapping(data["suggestedMapping"], data["availableColumns"])
    if not ctx.mapping:
        raise SoftFailure("Unable to derive mapping from infer output; adjust prompt or data.")


def normalize_mapping(suggested: list[dict[str, Any]], columns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    column_lookup = {col.get("name") or col.get("column"): col for col in columns}
    mapping: list[dict[str, Any]] = []
    for item in suggested:
        column = item.get("column") or item.get("source")
        if not column or column not in column_lookup:
            continue
        mapping.append(
            {
                "term": item.get("term") or column.split(".")[-1],
                "column": column,
                "role": item.get("role") or infer_role_from_column(column),
                "grain": item.get("grain"),
            }
        )
    return mapping


def infer_role_from_column(column: str) -> str:
    lowered = column.lower()
    if any(tok in lowered for tok in ("date", "time")):
        return "time"
    if any(tok in lowered for tok in ("amount", "sales", "revenue", "count", "qty")):
        return "measure"
    return "dimension"


def step_generate_sql(ctx: SmokeContext) -> None:
    assert ctx.db_name and ctx.spec and ctx.mapping
    payload = {"db": ctx.db_name, "mapping": ctx.mapping, "spec": ctx.spec}
    resp = ctx.request("POST", "/report/generateSQL", json=payload)
    if resp.status_code != 200:
        raise RuntimeError(f"generateSQL failed: {resp.status_code} {resp.text}")
    data = ensure_json(resp)
    sql_text = data.get("sql")
    if not isinstance(sql_text, str) or not sql_text.strip():
        raise RuntimeError("generateSQL returned empty SQL")
    columns = data.get("columns")
    if not isinstance(columns, list) or not columns:
        raise RuntimeError("generateSQL returned no columns")
    params = data.get("params")
    if not isinstance(params, list):
        raise RuntimeError("generateSQL params is not a list")
    ctx.sql_text = sql_text
    ctx.columns = columns
    ctx.params = params


def step_preview(ctx: SmokeContext) -> None:
    assert ctx.db_name and ctx.sql_text
    limit = int(env("TEST_PREVIEW_LIMIT"))
    params_dict: dict[str, Any] = {}
    for param in ctx.params:
        name = param.get("name")
        if not name:
            continue
        params_dict[name] = param.get("value") or ""
    payload = {"db": ctx.db_name, "sql": ctx.sql_text, "params": params_dict, "limit": limit}
    resp = ctx.request("POST", "/report/preview", json=payload)
    if resp.status_code != 200:
        raise RuntimeError(f"preview failed: {resp.status_code} {resp.text}")
    data = ensure_json(resp)
    rows = data.get("rows")
    if not isinstance(rows, list):
        raise RuntimeError("preview rows is not a list")
    row_count = data.get("row_count")
    if not isinstance(row_count, int):
        raise RuntimeError("preview row_count is not an int")
    if row_count > limit:
        raise RuntimeError("preview returned more rows than requested limit")


def step_publish(ctx: SmokeContext) -> None:
    assert ctx.db_name and ctx.sql_text and ctx.columns
    mapping = ctx.mapping
    columns = build_publish_columns(ctx.columns)
    parameters = build_publish_parameters(ctx.params)
    filters = build_publish_filters(parameters, columns)
    sort = build_publish_sort(columns)
    chart = build_publish_chart(columns)
    payload = {
        "db": {"name": ctx.db_name},
        "report": {
            "title": env("TEST_REPORT_TITLE"),
            "folder": env("TEST_FOLDER"),
            "shared_data_source_path": env("TEST_SHARED_DS_PATH"),
        },
        "mapping": mapping,
        "columns": columns,
        "parameters": parameters,
        "filters": filters,
        "sort": sort,
        "chart": chart,
    }
    ctx.publish_payload = payload
    resp = ctx.request("POST", "/report/publishReport", json=payload)
    data = ensure_json(resp)
    if resp.status_code == 200:
        render_url = data.get("render_url_pdf")
        print(f"Publish succeeded. Render URL: {render_url}")
        return
    message = data.get("error", {}).get("message", "")
    if resp.status_code in {400, 502} and "ssrs" in message.lower():
        raise SsrsUnavailable(f"Publish skipped: {message}")
    raise RuntimeError(f"publish failed: {resp.status_code} {data}")


def build_publish_columns(columns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for idx, column in enumerate(columns):
        result.append(
            {
                "name": column.get("name") or f"Field{idx}",
                "source": column.get("source") or column.get("name") or f"Field{idx}",
                "system_type_name": column.get("system_type_name"),
                "rdlType": column.get("rdlType") or infer_rdl_type(column.get("name", "")),
                "role": column.get("role") or infer_role_from_column(column.get("name", "")),
                "display_name": column.get("display_name") or column.get("name") or f"Field {idx}",
                "description": column.get("description"),
                "include": column.get("include", True),
                "agg": column.get("agg"),
                "format": column.get("format") or "None",
                "samples": column.get("samples"),
                "null_pct": column.get("null_pct"),
            }
        )
    return result


def build_publish_parameters(params: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for param in params:
        name = param.get("name")
        if not name:
            continue
        result.append(
            {
                "name": name.lstrip("@"),
                "rdlType": param.get("rdlType") or infer_rdl_type(name),
                "default": param.get("value"),
                "multi": param.get("multi"),
                "prompt": param.get("prompt"),
            }
        )
    return result


def build_publish_filters(params: list[dict[str, Any]], columns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    filters: list[dict[str, Any]] = []
    if not params or not columns:
        return filters
    target_column = next((col for col in columns if col.get("role") == "time"), columns[0])
    for param in params:
        filters.append(
            {
                "field": target_column["source"],
                "op": ">=",
                "param": param["name"],
            }
        )
    return filters


def build_publish_sort(columns: list[dict[str, Any]]) -> list[dict[str, Any]] | None:
    for column in columns:
        if column.get("role") in {"time", "dimension"}:
            return [{"field": column["name"], "dir": "asc"}]
    return None


def build_publish_chart(columns: list[dict[str, Any]]) -> dict[str, Any] | None:
    time_col = next((col for col in columns if col.get("role") == "time"), None)
    measure = next((col for col in columns if col.get("role") == "measure"), None)
    if not time_col or not measure:
        return None
    return {
        "type": "line",
        "category": time_col["name"],
        "series": [measure["name"]],
        "values": [measure["name"]],
    }


def infer_rdl_type(name: str) -> str:
    lowered = name.lower()
    if any(tok in lowered for tok in ("date", "time")):
        return "DateTime"
    if any(tok in lowered for tok in ("amt", "amount", "sales", "revenue", "price", "qty", "count")):
        return "Float"
    return "String"


def print_summary(results: list[StepResult], ssrs_warning: str | None) -> None:
    if not results:
        return
    print("\nSmoke Summary:")
    for result in results:
        status = "✅" if result.success else "❌"
        print(f" {status} {result.name} ({result.duration:.2f}s) - {result.message}")
    if ssrs_warning:
        print(f" ⚠️  {ssrs_warning}")


def main() -> None:
    ctx = SmokeContext()
    steps = [
        ("customerDatabases", lambda: step_customer_databases(ctx)),
        ("inferFromNaturalLanguage", lambda: step_infer(ctx)),
        ("generateSQL", lambda: step_generate_sql(ctx)),
        ("preview", lambda: step_preview(ctx)),
        ("publishReport", lambda: step_publish(ctx)),
    ]
    for name, func in steps:
        ctx.record(name, func)
    print_summary(ctx.summaries, ctx.ssrs_warning)


if __name__ == "__main__":  # pragma: no cover - CLI entry
    main()
