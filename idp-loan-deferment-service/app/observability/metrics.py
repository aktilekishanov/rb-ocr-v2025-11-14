from __future__ import annotations

import time
from typing import Callable, Awaitable

from fastapi import APIRouter, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

try:
    from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
except Exception:  # pragma: no cover
    # Lightweight fallbacks so code does not crash if dependency is missing
    Counter = None  # type: ignore
    Histogram = None  # type: ignore
    def generate_latest():  # type: ignore
        return b""
    CONTENT_TYPE_LATEST = "text/plain; version=0.0.4"  # type: ignore


# Metrics primitives (no-op if prometheus_client is missing)
if Counter is not None and Histogram is not None:
    http_requests_total = Counter(
        "http_requests_total",
        "Total HTTP requests processed",
        labelnames=("endpoint", "method", "status"),
    )
    http_request_duration_seconds = Histogram(
        "http_request_duration_seconds",
        "HTTP request duration in seconds",
        labelnames=("endpoint", "method"),
        buckets=(0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 5.0, 10.0),
    )
    pipeline_duration_seconds = Histogram(
        "pipeline_duration_seconds",
        "End-to-end pipeline duration in seconds",
        buckets=(0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 60.0, 120.0),
    )
    pipeline_stage_duration_seconds = Histogram(
        "pipeline_stage_duration_seconds",
        "Pipeline stage duration in seconds",
        labelnames=("stage",),
        buckets=(0.01, 0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 5.0),
    )
    jobs_submitted_total = Counter("jobs_submitted_total", "Jobs submitted")
    jobs_completed_total = Counter("jobs_completed_total", "Jobs completed successfully")
    jobs_failed_total = Counter("jobs_failed_total", "Jobs failed")
else:  # pragma: no cover
    http_requests_total = None  # type: ignore
    http_request_duration_seconds = None  # type: ignore
    pipeline_duration_seconds = None  # type: ignore
    pipeline_stage_duration_seconds = None  # type: ignore
    jobs_submitted_total = None  # type: ignore
    jobs_completed_total = None  # type: ignore
    jobs_failed_total = None  # type: ignore


class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]):
        if http_requests_total is None:
            # Metrics disabled, just pass through
            return await call_next(request)
        start = time.perf_counter()
        try:
            response = await call_next(request)
            status = getattr(response, "status_code", 200)
            endpoint = _endpoint_label(request)
            method = request.method
            http_requests_total.labels(endpoint=endpoint, method=method, status=str(status)).inc()
            http_request_duration_seconds.labels(endpoint=endpoint, method=method).observe(time.perf_counter() - start)
            return response
        except Exception:
            endpoint = _endpoint_label(request)
            method = request.method
            http_requests_total.labels(endpoint=endpoint, method=method, status="500").inc()
            http_request_duration_seconds.labels(endpoint=endpoint, method=method).observe(time.perf_counter() - start)
            raise


def _endpoint_label(request: Request) -> str:
    # Try to use the route path template (e.g., /v1/jobs/{run_id})
    route = request.scope.get("route")
    path = getattr(route, "path", None) or getattr(route, "path_format", None)
    if isinstance(path, str) and path:
        return path
    return request.url.path


def record_pipeline_duration(seconds: float) -> None:
    if pipeline_duration_seconds is not None:
        pipeline_duration_seconds.observe(seconds)


def inc_job_submitted() -> None:
    if jobs_submitted_total is not None:
        jobs_submitted_total.inc()


def inc_job_completed() -> None:
    if jobs_completed_total is not None:
        jobs_completed_total.inc()


def inc_job_failed() -> None:
    if jobs_failed_total is not None:
        jobs_failed_total.inc()


def record_stage_duration(stage: str, seconds: float) -> None:
    if pipeline_stage_duration_seconds is not None:
        pipeline_stage_duration_seconds.labels(stage=stage).observe(seconds)


# Router to expose /metrics
router = APIRouter()


@router.get("/metrics")
async def metrics_endpoint():
    data = generate_latest()
    return Response(content=data, media_type=CONTENT_TYPE_LATEST)
