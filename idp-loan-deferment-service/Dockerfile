# Multi-stage Dockerfile for idp-loan-deferment-service

# ---------- Builder stage: build wheels to keep final image small ----------
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install build deps only in builder stage
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential gcc \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies into wheels
COPY requirements.txt ./
RUN python -m pip install --upgrade pip \
    && pip wheel --no-cache-dir --no-deps --wheel-dir /wheels -r requirements.txt

# ---------- Runtime stage: minimal image with deps installed from wheels ----------
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Create non-root user
RUN addgroup --system app && adduser --system --ingroup app appuser

# Copy dependency wheels and install
COPY --from=builder /wheels /wheels
RUN python -m pip install --upgrade pip \
    && pip install --no-cache-dir /wheels/* \
    && rm -rf /wheels

# Copy application code
COPY . /app

# Prepare runs dir and permissions
RUN mkdir -p /app/runs && chown -R appuser:app /app

USER appuser

# Default runs dir inside container
ENV IDP_RUNS_DIR=/app/runs

EXPOSE 8000

# Gunicorn + Uvicorn worker
CMD ["gunicorn", "-k", "uvicorn.workers.UvicornWorker", "-w", "2", "-b", "0.0.0.0:8000", "app.main:app"]
