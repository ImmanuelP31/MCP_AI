from __future__ import annotations

from contextvars import ContextVar, Token
from dataclasses import dataclass
from uuid import uuid4

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
correlation_id_var: ContextVar[str | None] = ContextVar("correlation_id", default=None)
trace_id_var: ContextVar[str | None] = ContextVar("trace_id", default=None)
span_id_var: ContextVar[str | None] = ContextVar("span_id", default=None)


@dataclass(frozen=True, slots=True)
class ObservabilityContextTokens:
    request_id: Token[str | None]
    correlation_id: Token[str | None]
    trace_id: Token[str | None]
    span_id: Token[str | None]


def new_request_id() -> str:
    return str(uuid4())


def new_trace_id() -> str:
    return uuid4().hex


def new_span_id() -> str:
    return uuid4().hex[:16]


def set_observability_context(
    *,
    request_id: str | None = None,
    correlation_id: str | None = None,
    trace_id: str | None = None,
    span_id: str | None = None,
) -> ObservabilityContextTokens:
    resolved_request_id = request_id or new_request_id()
    resolved_correlation_id = correlation_id or resolved_request_id
    return ObservabilityContextTokens(
        request_id=request_id_var.set(resolved_request_id),
        correlation_id=correlation_id_var.set(resolved_correlation_id),
        trace_id=trace_id_var.set(trace_id or new_trace_id()),
        span_id=span_id_var.set(span_id or new_span_id()),
    )


def reset_observability_context(tokens: ObservabilityContextTokens) -> None:
    request_id_var.reset(tokens.request_id)
    correlation_id_var.reset(tokens.correlation_id)
    trace_id_var.reset(tokens.trace_id)
    span_id_var.reset(tokens.span_id)


def current_request_id() -> str | None:
    return request_id_var.get()


def current_correlation_id() -> str | None:
    return correlation_id_var.get()


def current_trace_id() -> str | None:
    return trace_id_var.get()


def current_span_id() -> str | None:
    return span_id_var.get()
