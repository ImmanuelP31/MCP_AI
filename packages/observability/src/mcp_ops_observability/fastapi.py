from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from prometheus_client import CONTENT_TYPE_LATEST
from starlette.responses import Response as StarletteResponse

from mcp_ops_observability.context import (
    current_correlation_id,
    current_request_id,
    reset_observability_context,
    set_observability_context,
)
from mcp_ops_observability.metrics import metrics_response, record_api_request
from mcp_ops_observability.tracing import current_traceparent, parse_traceparent, start_span

logger = logging.getLogger("mcp_ops.api")


def add_observability(app: FastAPI) -> None:
    @app.middleware("http")
    async def observability_middleware(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        started = time.perf_counter()
        request_id = request.headers.get("x-request-id")
        correlation_id = request.headers.get("x-correlation-id")
        trace_context = parse_traceparent(request.headers.get("traceparent"))
        tokens = set_observability_context(
            request_id=request_id,
            correlation_id=correlation_id,
            trace_id=trace_context.trace_id,
            span_id=trace_context.span_id,
        )
        status_code = 500
        try:
            with start_span("api.request", method=request.method, path=request.url.path):
                response = await call_next(request)
            status_code = response.status_code
            return _with_observability_headers(response)
        except Exception:
            logger.exception(
                "api.request.failed",
                extra={"method": request.method, "path": request.url.path},
            )
            raise
        finally:
            latency_seconds = time.perf_counter() - started
            record_api_request(request.method, request.url.path, status_code, latency_seconds)
            logger.info(
                "api.request.completed",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": status_code,
                    "latency_ms": round(latency_seconds * 1000, 3),
                },
            )
            reset_observability_context(tokens)

    @app.get("/metrics", include_in_schema=False)
    def prometheus_metrics() -> StarletteResponse:
        return StarletteResponse(content=metrics_response(), media_type=CONTENT_TYPE_LATEST)


def _with_observability_headers(response: Response) -> Response:
    request_id = current_request_id()
    correlation_id = current_correlation_id()
    if request_id:
        response.headers["x-request-id"] = request_id
    if correlation_id:
        response.headers["x-correlation-id"] = correlation_id
    traceparent = current_traceparent()
    if traceparent:
        response.headers["traceparent"] = traceparent
    return response
