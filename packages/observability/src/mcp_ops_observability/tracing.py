from __future__ import annotations

import logging
import re
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

from mcp_ops_observability.context import (
    current_span_id,
    current_trace_id,
    new_span_id,
    new_trace_id,
    span_id_var,
    trace_id_var,
)

TRACEPARENT_RE = re.compile(
    r"^(?P<version>[0-9a-f]{2})-(?P<trace_id>[0-9a-f]{32})-"
    r"(?P<span_id>[0-9a-f]{16})-(?P<flags>[0-9a-f]{2})$"
)
logger = logging.getLogger("mcp_ops.tracing")


@dataclass(frozen=True, slots=True)
class TraceContext:
    trace_id: str
    span_id: str
    sampled: bool = True

    def traceparent(self) -> str:
        flags = "01" if self.sampled else "00"
        return f"00-{self.trace_id}-{self.span_id}-{flags}"


def parse_traceparent(value: str | None) -> TraceContext:
    if not value:
        return TraceContext(trace_id=new_trace_id()[:32], span_id=new_span_id())
    match = TRACEPARENT_RE.match(value.lower())
    if match is None:
        return TraceContext(trace_id=new_trace_id()[:32], span_id=new_span_id())
    return TraceContext(
        trace_id=match.group("trace_id"),
        span_id=match.group("span_id"),
        sampled=match.group("flags") == "01",
    )


def current_traceparent() -> str | None:
    trace_id = current_trace_id()
    span_id = current_span_id()
    if trace_id is None or span_id is None:
        return None
    return TraceContext(trace_id=trace_id[:32], span_id=span_id[:16]).traceparent()


@contextmanager
def start_span(name: str, **attributes: object) -> Iterator[TraceContext]:
    parent_trace_id = current_trace_id() or new_trace_id()[:32]
    span_id = new_span_id()
    trace_token = trace_id_var.set(parent_trace_id[:32])
    span_token = span_id_var.set(span_id)
    started = time.perf_counter()
    context = TraceContext(trace_id=parent_trace_id[:32], span_id=span_id)
    try:
        logger.info("span.start", extra={"span_name": name, "span_attributes": attributes})
        yield context
        logger.info(
            "span.end",
            extra={
                "span_name": name,
                "span_attributes": attributes,
                "duration_ms": round((time.perf_counter() - started) * 1000, 3),
            },
        )
    except Exception:
        logger.exception(
            "span.error",
            extra={
                "span_name": name,
                "span_attributes": attributes,
                "duration_ms": round((time.perf_counter() - started) * 1000, 3),
            },
        )
        raise
    finally:
        span_id_var.reset(span_token)
        trace_id_var.reset(trace_token)
