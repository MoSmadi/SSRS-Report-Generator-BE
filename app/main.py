"""FastAPI application entrypoint."""
from __future__ import annotations

import logging
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .config import get_settings
from .models import ServiceError, format_error
from .routers.report import router as report_router
from .utils.logging import bind_request_context, configure_logging

settings = get_settings()
configure_logging(settings.log_level)
logger = logging.getLogger("app")

app = FastAPI(title="NL to SSRS Backend", version="1.0.0")


@app.exception_handler(ServiceError)
async def service_error_handler(request: Request, exc: ServiceError):
    logger.warning(
        "service error",
        extra={**bind_request_context(request), "status_code": exc.status_code, "error_code": exc.code},
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=format_error(exc.message, exc.code),
    )


@app.exception_handler(Exception)
async def default_exception_handler(request: Request, exc: Exception):  # pragma: no cover - fallback
    logger.exception("uncaught exception", extra=bind_request_context(request))
    return JSONResponse(
        status_code=500,
        content=format_error("Internal server error", "internal_error"),
    )


@app.middleware("http")
async def request_context_middleware(request: Request, call_next):
    request.state.request_id = str(uuid.uuid4())
    context = bind_request_context(request)
    start = time.perf_counter()
    try:
        response = await call_next(request)
    except ServiceError:
        raise
    except Exception:  # pragma: no cover - handled by exception handler
        context["duration_ms"] = round((time.perf_counter() - start) * 1000, 2)
        logger.exception("unhandled error", extra=context)
        raise
    context["status_code"] = response.status_code
    context["duration_ms"] = round((time.perf_counter() - start) * 1000, 2)
    logger.info("request", extra=context)
    return response


@app.get("/healthz", tags=["meta"])
async def health() -> dict[str, bool]:
    return {"ok": True}


app.include_router(report_router)
