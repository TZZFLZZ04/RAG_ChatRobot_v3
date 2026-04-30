from __future__ import annotations

from contextvars import ContextVar, Token
from typing import Any

_request_id_ctx: ContextVar[str | None] = ContextVar("request_id", default=None)
_correlation_id_ctx: ContextVar[str | None] = ContextVar("correlation_id", default=None)
_task_id_ctx: ContextVar[str | None] = ContextVar("task_id", default=None)


def set_context(
    *,
    request_id: str | None = None,
    correlation_id: str | None = None,
    task_id: str | None = None,
) -> dict[str, Token[str | None]]:
    tokens: dict[str, Token[str | None]] = {}
    if request_id is not None:
        tokens["request_id"] = _request_id_ctx.set(request_id)
    if correlation_id is not None:
        tokens["correlation_id"] = _correlation_id_ctx.set(correlation_id)
    if task_id is not None:
        tokens["task_id"] = _task_id_ctx.set(task_id)
    return tokens


def reset_context(tokens: dict[str, Token[str | None]]) -> None:
    if "task_id" in tokens:
        _task_id_ctx.reset(tokens["task_id"])
    if "correlation_id" in tokens:
        _correlation_id_ctx.reset(tokens["correlation_id"])
    if "request_id" in tokens:
        _request_id_ctx.reset(tokens["request_id"])


def get_request_id() -> str | None:
    return _request_id_ctx.get()


def get_correlation_id() -> str | None:
    return _correlation_id_ctx.get()


def get_task_id() -> str | None:
    return _task_id_ctx.get()


def get_log_context() -> dict[str, Any]:
    context: dict[str, Any] = {}
    request_id = get_request_id()
    correlation_id = get_correlation_id()
    task_id = get_task_id()

    if request_id:
        context["request_id"] = request_id
    if correlation_id:
        context["correlation_id"] = correlation_id
    if task_id:
        context["task_id"] = task_id

    trace_context = _get_trace_context()
    context.update(trace_context)
    return context


def _get_trace_context() -> dict[str, str]:
    try:
        from opentelemetry import trace
    except ImportError:
        return {}

    span = trace.get_current_span()
    if span is None:
        return {}

    span_context = span.get_span_context()
    if not span_context or not span_context.is_valid:
        return {}

    return {
        "trace_id": f"{span_context.trace_id:032x}",
        "span_id": f"{span_context.span_id:016x}",
    }
