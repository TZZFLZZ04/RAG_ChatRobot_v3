from __future__ import annotations

from fastapi import Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

http_requests_total = Counter(
    "chatrobot_http_requests_total",
    "Total number of HTTP requests handled by the API.",
    ("method", "path", "status_code"),
)
http_request_latency_seconds = Histogram(
    "chatrobot_http_request_latency_seconds",
    "HTTP request latency in seconds.",
    ("method", "path"),
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, float("inf")),
)
http_errors_total = Counter(
    "chatrobot_http_errors_total",
    "Total number of HTTP errors returned by the API.",
    ("method", "path", "error_code"),
)
celery_tasks_total = Counter(
    "chatrobot_celery_tasks_total",
    "Total number of Celery task executions.",
    ("task_name", "state"),
)
celery_task_latency_seconds = Histogram(
    "chatrobot_celery_task_latency_seconds",
    "Celery task execution latency in seconds.",
    ("task_name", "state"),
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 3.0, 5.0, 10.0, 30.0, 60.0, float("inf")),
)


def get_request_path(request) -> str:
    route = request.scope.get("route")
    route_path = getattr(route, "path", None)
    if route_path:
        return route_path
    return request.url.path


def observe_http_request(*, request, status_code: int, duration_seconds: float) -> None:
    method = request.method
    path = get_request_path(request)
    status_label = str(status_code)

    http_requests_total.labels(method=method, path=path, status_code=status_label).inc()
    http_request_latency_seconds.labels(method=method, path=path).observe(duration_seconds)


def observe_http_error(*, request, error_code: str) -> None:
    http_errors_total.labels(
        method=request.method,
        path=get_request_path(request),
        error_code=error_code,
    ).inc()


def observe_celery_task(*, task_name: str, state: str, duration_seconds: float | None) -> None:
    celery_tasks_total.labels(task_name=task_name, state=state).inc()
    if duration_seconds is not None:
        celery_task_latency_seconds.labels(task_name=task_name, state=state).observe(duration_seconds)


def render_metrics_response() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
