"""Pydantic schemas describing external API contracts."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

RdlType = Literal["String", "Integer", "Float", "DateTime", "Boolean"]
Role = Literal["measure", "dimension", "time"]
Grain = Literal["day", "week", "month", "quarter", "year"]


class DbRef(BaseModel):
    name: str


class ReportTarget(BaseModel):
    title: str
    folder: str
    shared_data_source_path: str


class Mapping(BaseModel):
    term: str
    column: str
    role: Role
    grain: Grain | None = None


class ColumnDef(BaseModel):
    name: str
    source: str
    system_type_name: str | None = None
    rdlType: RdlType
    role: Role
    display_name: str
    description: str | None = None
    include: bool = True
    agg: Literal["SUM", "AVG", "COUNT"] | None = None
    format: Literal["Currency", "Number", "Percent", "None"] | None = None
    samples: list[str] | None = None
    null_pct: float | None = None


class ParamDef(BaseModel):
    name: str
    rdlType: RdlType
    default: str | int | float | bool | list[str] | None = None
    multi: bool | None = None
    prompt: str | None = None


class FilterDef(BaseModel):
    field: str
    op: Literal["=", ">=", "<=", "<", ">", "<>", "in", "like"]
    param: str


class SortDef(BaseModel):
    field: str
    dir: Literal["asc", "desc"]


class ChartSpec(BaseModel):
    type: Literal["line", "column", "area"]
    category: str
    series: list[str] = Field(default_factory=list)
    values: list[str]


class InferIn(BaseModel):
    db: str
    title: str
    text: str


class InferOut(BaseModel):
    spec: dict
    suggestedMapping: list[Mapping]
    availableColumns: list[dict]
    notes: str | None = None


class GenSQLIn(BaseModel):
    db: str
    mapping: list[Mapping]
    spec: dict


class GenSQLOut(BaseModel):
    sql: str
    params: list[dict]
    columns: list[ColumnDef]


class PreviewIn(BaseModel):
    db: str
    sql: str
    params: dict
    limit: int = 20


class PreviewOut(BaseModel):
    rows: list[dict]
    row_count: int


class PublishIn(BaseModel):
    db: DbRef
    report: ReportTarget
    mapping: list[Mapping]
    columns: list[ColumnDef]
    parameters: list[ParamDef]
    filters: list[FilterDef]
    sort: list[SortDef] | None = None
    chart: ChartSpec | None = None


class PublishOut(BaseModel):
    path: str
    render_url_pdf: str
    server: dict | None = None
    dataset_fields: list[dict]
    echo: dict


class ErrorSchema(BaseModel):
    error: dict
