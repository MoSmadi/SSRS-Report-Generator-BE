"""Domain helpers shared across modules."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional


@dataclass
class QueryParameter:
    """Represents a SQL parameter definition used for SSRS datasets."""

    name: str
    type: str
    default: Optional[Any] = None


@dataclass
class DatasetField:
    """Normalized dataset field metadata consumed by RDL builder."""

    name: str
    rdl_type: str
    display_name: str
    description: Optional[str] = None


@dataclass
class PaginatedRows:
    """Lightweight holder for preview data."""

    rows: List[Dict[str, Any]]
    total: int

    @classmethod
    def from_iterable(cls, data: Iterable[dict[str, Any]]) -> "PaginatedRows":
        data_list = list(data)
        return cls(rows=data_list, total=len(data_list))


class ServiceError(Exception):
    """Custom exception that drives uniform API error responses."""

    def __init__(self, message: str, code: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code


def format_error(message: str, code: str) -> dict[str, dict[str, str]]:
    return {"error": {"message": message, "code": code}}
