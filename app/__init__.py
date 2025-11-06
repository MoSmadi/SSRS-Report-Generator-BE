"""FastAPI application package for automated SSRS report generation."""

from .config import get_settings  # re-export for convenience

__all__ = ["get_settings"]
