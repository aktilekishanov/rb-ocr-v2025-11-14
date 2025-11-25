from __future__ import annotations

from typing import Any

from app.core.logging import get_logger


def init_tracing_if_enabled(settings: Any) -> None:
    """
    Initialize OpenTelemetry tracing if enabled via settings and if dependencies are present.
    This is a no-op when disabled or when OTel packages are not installed.
    """
    logger = get_logger(__name__)

    enabled = getattr(settings, "TRACING_ENABLED", False)
    if not enabled:
        return

    try:
        # Optional imports guarded behind try/except to avoid hard dependency
        from opentelemetry import trace  # type: ignore
        from opentelemetry.sdk.resources import Resource  # type: ignore
        from opentelemetry.sdk.trace import TracerProvider  # type: ignore
        from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter  # type: ignore
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor  # type: ignore
    except Exception:
        logger.warning("tracing_init_skipped_missing_deps")
        return

    try:
        service_name = getattr(settings, "APP_NAME", "idp-loan-deferment-service")
        resource = Resource.create({"service.name": service_name})
        provider = TracerProvider(resource=resource)
        processor = BatchSpanProcessor(ConsoleSpanExporter())
        provider.add_span_processor(processor)
        trace.set_tracer_provider(provider)

        # Instrumentation of FastAPI will be applied when app instance is available
        # (FastAPIInstrumentor.instrument_app(app)) – we'll call this from main if needed.
        logger.info("tracing_initialized", extra={"service": service_name})
    except Exception as e:
        logger.warning("tracing_init_failed", extra={"error": str(e)})
        return


def instrument_app_if_tracing_enabled(app: Any, settings: Any) -> None:
    """Instrument FastAPI app with OpenTelemetry if enabled and deps are present.
    Safe no-op otherwise.
    """
    logger = get_logger(__name__)
    enabled = getattr(settings, "TRACING_ENABLED", False)
    if not enabled:
        return
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor  # type: ignore
    except Exception:
        logger.warning("tracing_instrumentation_skipped_missing_deps")
        return
    try:
        FastAPIInstrumentor().instrument_app(app)
        logger.info("tracing_app_instrumented")
    except Exception as e:
        logger.warning("tracing_instrumentation_failed", extra={"error": str(e)})
