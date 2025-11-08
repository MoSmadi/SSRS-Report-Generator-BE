"""Pydantic schemas describing external API contracts."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Union
from typing import Literal

from pydantic import BaseModel, Field, ConfigDict

RdlType = Literal["String", "Integer", "Float", "DateTime", "Boolean"]
Role = Literal["measure", "dimension", "time", "metric"]
SuggestedRole = Literal["metric", "dimension"]
Grain = Literal["day", "week", "month", "quarter", "year"]
IntentGrain = Literal["day", "week", "month", "quarter", "year", "none"]


class IntentFilter(BaseModel):
    field: str
    operator: str
    value: str


class ChartIntent(BaseModel):
    type: Literal["table", "line", "bar", "pie"]
    x: str
    y: str
    series: Optional[List[str]] = None


class NLSpec(BaseModel):
    title: str
    metrics: List[str] = Field(default_factory=list)
    dimensions: List[str] = Field(default_factory=list)
    filters: List[IntentFilter] = Field(default_factory=list)
    grain: IntentGrain = "none"
    chart: Optional[ChartIntent] = None


class DbRef(BaseModel):
    name: str


class ReportTarget(BaseModel):
    title: str
    folder: str
    shared_data_source_path: str


class Mapping(BaseModel):
    term: str
    column: Optional[str] = None
    role: Role
    grain: Optional[Grain] = None


class SuggestedMappingItem(BaseModel):
    term: str
    role: SuggestedRole
    column: Optional[str] = None
    confidence: Optional[float] = None
    reason: Optional[str] = None
    grain: Optional[Grain] = None


class ColumnDef(BaseModel):
    name: str
    source: str
    system_type_name: Optional[str] = None
    rdlType: RdlType
    role: Role
    display_name: str
    description: Optional[str] = None
    include: bool = True
    agg: Optional[Literal["SUM", "AVG", "COUNT"]] = None
    format: Optional[Literal["Currency", "Number", "Percent", "None"]] = None
    samples: Optional[List[str]] = None
    null_pct: Optional[float] = None


class ParamDef(BaseModel):
    name: str
    rdlType: RdlType
    default: Optional[Union[str, int, float, bool, List[str]]] = None
    multi: Optional[bool] = None
    prompt: Optional[str] = None


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
    series: List[str] = Field(default_factory=list)
    values: List[str]


class InferIn(BaseModel):
    db: str
    title: str
    text: str


class InferOut(BaseModel):
    spec: Dict[str, Any]
    suggestedMapping: List[SuggestedMappingItem]
    availableColumns: List[Dict[str, Any]]
    schemaInsights: SchemaInsights


class GenSQLIn(BaseModel):
    db: str
    mapping: List[Mapping]
    spec: Dict[str, Any]


class GenSQLOut(BaseModel):
    sql: str
    params: List[Dict[str, Any]]
    columns: List[ColumnDef]


class PreviewIn(BaseModel):
    db: str
    sql: str
    params: Dict[str, Any] = Field(default_factory=dict)
    limit: int = 100


class PreviewOut(BaseModel):
    rows: List[Dict[str, Any]]
    row_count: int


class PublishIn(BaseModel):
    db: DbRef
    report: ReportTarget
    mapping: List[Mapping]
    columns: List[ColumnDef]
    parameters: List[ParamDef]
    filters: List[FilterDef]
    sort: Optional[List[SortDef]] = None
    chart: Optional[ChartSpec] = None


class PublishOut(BaseModel):
    path: str
    render_url_pdf: str
    server: Optional[Dict[str, Any]] = None
    dataset_fields: List[Dict[str, Any]]
    echo: Dict[str, Any]


class ErrorSchema(BaseModel):
    error: Dict[str, Any]


class ColumnMetadata(BaseModel):
    schema: str
    table: str
    column: str
    dataType: str
    isNumeric: bool
    isDateLike: bool
    sampleValues: Optional[List[str]] = None
    name: Optional[str] = None
    bracketedName: Optional[str] = None

    @property
    def qualified_name(self) -> str:
        if self.bracketedName:
            return self.bracketedName
        if self.name and self.name.startswith("["):
            return self.name
        return f"[{self.schema}].[{self.table}].[{self.column}]"

    model_config = ConfigDict(protected_namespaces=())


class MissingFieldSuggestion(BaseModel):
    name: str
    suggestions: List[str] = Field(default_factory=list)


class SchemaInsights(BaseModel):
    coveragePercent: int
    matchedFields: List[str] = Field(default_factory=list)
    missingFields: List[MissingFieldSuggestion] = Field(default_factory=list)
