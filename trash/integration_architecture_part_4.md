# Integration Architecture – Part 4: Pipeline Hardening

This document describes how to harden the IDP loan deferment pipeline for **throughput, latency, and stability**. It focuses on:

- Batch/async processing model for Kafka-driven workloads.
- Configurable timeouts for OCR/LLM and external I/O.
- Memory/CPU usage controls.
- Concurrency control and backpressure.

It assumes:
- The **microservice foundation** is in place (see `integration_architecture_part_1.md`).
- Kafka, MinIO, and callback wiring are introduced in other parts.

---

## 1. Goals and non-goals

### 1.1. Goals

- **Predictable latency**: bound worst-case processing times with configurable timeouts per stage.
- **Safe throughput scaling**: the service can handle higher Kafka rates by scaling horizontally or tuning concurrency.
- **Resource safety**: avoid OOMs and CPU starvation due to heavy OCR/LLM calls or oversized documents.
- **Graceful degradation**: on overload or partial failures, fail requests predictably (with clear error codes) instead of hanging.

### 1.2. Non-goals (for now)

- Advanced **dynamic autoscaling** logic (HPA based on custom metrics) – can be added later.
- Cross-pipeline scheduling or multi-tenant isolation – we design with it in mind but keep implementation simple.

---

## 2. Conceptual model

The core pipeline stages for each document:

1. Pre-processing (PDF/image handling).
2. OCR.
3. LLM extraction.
4. Business validation.
5. Persistence + callback.

**Hardening** introduces:

- **Async execution**: each Kafka message is processed concurrently up to a configurable limit.
- **Stage-level timeouts**: each stage has its own max duration; if exceeded, the pipeline fails fast with a clear error.
- **Per-run context**: a `PipelineContext` object carries timing, limits, and cancellation flags.
- **Backpressure**: when the system is at capacity, we slow or pause Kafka consumption.

---

## 3. Batch and async processing strategy

### 3.1. Processing unit

- **Unit of work**: one Kafka message = one document processing run (one `request_id`, one `run_id`).
- We do not batch multiple documents from a single message in v1; batch support can be added later.

### 3.2. Async/concurrent model

Use **asyncio** for the worker:

- Kafka consumer loop pulls messages and submits them to an **async task pool**.
- Limit concurrent tasks to `max_concurrent_runs` (config-driven).

Implementation outline (conceptual):

- In `service/consumer.py`:
  - Maintain a semaphore, e.g. `concurrency_semaphore = asyncio.Semaphore(settings.max_concurrent_runs)`.
  - For each polled Kafka message:
    - `await concurrency_semaphore.acquire()`.
    - Start `asyncio.create_task(process_message(msg, semaphore))` where `process_message` ensures `semaphore.release()` on completion.

- `process_message` will:
  - Deserialize event and build a `PipelineContext`.
  - Call the orchestrator adapter (`run_pipeline_with_timeouts(ctx, payload)`).
  - Handle success/failure, ack/commit or send to DLQ as per error policy (see other parts).

### 3.3. Optional batch improvements

Later, if needed:

- Use Kafka’s batch fetch to pull multiple messages at once.
- Still process each message as an independent task, but in groups for efficiency.

---

## 4. Timeouts and cancellation

### 4.1. Timeout configuration

In `service/config.py`, add:

- `pipeline_total_timeout_ms` – max total duration for a pipeline run.
- `timeout_fetch_ms` – Max time for MinIO fetch.
- `timeout_ocr_ms` – Max time for OCR step.
- `timeout_llm_ms` – Max time for LLM call.
- `timeout_validate_ms` – Max time for business validation.
- `timeout_callback_ms` – Max time for REST callback.

These should have sane defaults for dev and be overridable via env.

### 4.2. Implementation approach

In a `pipeline_adapter` module (or inside orchestrator stages):

- Wrap each stage with a **timeout utility**, e.g. `await asyncio.wait_for(stage_fn(...), timeout=timeout_s)`.
- On timeout:
  - Mark the stage as failed with an explicit error code, e.g. `"TIMEOUT_OCR"`, `"TIMEOUT_LLM"`.
  - Cancel or skip remaining stages.
  - Persist a failure result and still attempt callback with `status="failed"`.

### 4.3. Cancellation and cooperative checks

- Propagate a cancellation flag via `PipelineContext`, so long-running synchronous code (like heavy PDF parsing) can periodically check `ctx.cancelled` and abort if set.
- For pure sync code where `asyncio.wait_for` doesn’t help, use thread pool executors and interrupt at task boundaries (not mid-OCR call) – acceptable in v1.

---

## 5. Memory and CPU limits

### 5.1. Configurable resource hints

Extend `Settings` with:

- `max_document_size_mb` – reject or truncate documents exceeding this limit.
- `max_parallel_ocr` – upper bound for concurrent OCR tasks.
- `max_parallel_llm` – upper bound for concurrent LLM calls (and/or QPS).

These help enforce soft limits at the application level, on top of container-level limits.

### 5.2. Application-level controls

- **Document size check** during pre-processing:
  - If document size > `max_document_size_mb`, immediately fail with a specific error (e.g., `"DOC_TOO_LARGE"`).

- **Separate semaphores** for heavy stages:
  - `ocr_semaphore = asyncio.Semaphore(settings.max_parallel_ocr)`.
  - `llm_semaphore = asyncio.Semaphore(settings.max_parallel_llm)`.
  - Within each stage wrapper: `async with ocr_semaphore: await run_ocr(...)`.

- **Avoid unbounded in-memory structures**:
  - Stream data where possible (e.g. PDF pages) instead of loading everything at once.
  - Drop intermediate large images as soon as each stage is done.

### 5.3. Container-level limits

Coordinate with deployment team to set:

- `resources.requests/limits` in Kubernetes (CPU, memory).
- Configure horizontal scaling based on metrics like CPU, in-flight requests, or Kafka lag.

---

## 6. Concurrency control and backpressure

### 6.1. Concurrency knobs

From config:

- `max_concurrent_runs` – max in-flight pipeline runs per process.
- `max_parallel_ocr`, `max_parallel_llm` – stage-specific concurrency.

These allow tuning based on environment:

- `dev`: small numbers, easier debugging.
- `stage/prod`: higher values but still safe given CPU/LLM quotas.

### 6.2. Backpressure on Kafka consumption

In `consumer.py`:

- Use the main semaphore to determine whether to fetch more messages.
- If `concurrency_semaphore` has no capacity:
  - Pause `poll` or commit offsets only up to processed messages.
  - Some Kafka clients allow `pause`/`resume` per partition; use this if available.

This ensures we don’t accumulate an unbounded backlog in memory.

### 6.3. Slow consumer behavior

- Monitor **Kafka lag** metrics.
- If lag is consistently high:
  - Scale out: increase number of consumer instances (horizontal scaling).
  - Or tune down timeouts / cost of LLM calls, or increase concurrency (within safe resource bounds).

---

## 7. Integration with orchestrator design

Assuming the orchestrator has a **stage-based** architecture and a `PipelineContext`:

- Extend `PipelineContext` with:
  - `timeouts` (per-stage values taken from `Settings`).
  - `started_at`, `deadline` for total timeout.
  - `cancelled` flag.
- Wrap each stage invocation through a generic helper, e.g. `run_stage_with_limits(stage_name, fn, ctx, *args)` that:
  - Applies `asyncio.wait_for` with stage timeout.
  - Enforces stage-specific semaphores (OCR/LLM).
  - Records per-stage timing into `ctx.timings`.
  - On exception, attaches structured error info.

This preserves the existing pipeline logic but adds cross-cutting guarantees.

---

## 8. Configuration surface (summary)

Add the following to `Settings` (names can be adjusted to match your style):

- **Concurrency**
  - `max_concurrent_runs: int = 4`
  - `max_parallel_ocr: int = 2`
  - `max_parallel_llm: int = 2`

- **Timeouts (ms)**
  - `pipeline_total_timeout_ms: int = 600000`  # 10 minutes
  - `timeout_fetch_ms: int = 30000`
  - `timeout_ocr_ms: int = 120000`
  - `timeout_llm_ms: int = 120000`
  - `timeout_validate_ms: int = 30000`
  - `timeout_callback_ms: int = 30000`

- **Resource limits**
  - `max_document_size_mb: int = 20`

Values above are examples; tune based on real performance tests.

---

## 9. Metrics and observability for hardening

To verify and tune hardening, add metrics (e.g. via Prometheus) for:

- **Per-stage timing**: histograms for fetch, OCR, LLM, validate, callback.
- **Timeout counts** per stage and total.
- **In-flight runs** (current semaphore usage).
- **Queue/backlog indicators**: Kafka lag, number of pending tasks.
- **Error rate by code**: timeouts, external dependency failures, validation errors.

These metrics will drive adjustments to timeouts, concurrency, and autoscaling later.

---

## 10. Step-by-step implementation plan (Part 4)

1. **Extend config (`Settings`)**
   - Add concurrency, timeout, and resource limit fields listed above.
   - Expose them via env vars with sensible defaults for dev.

2. **Extend `PipelineContext` and orchestrator utilities**
   - Add timeout configuration, per-stage timing, and `cancelled` flag.
   - Introduce `run_stage_with_limits` helper and integrate with existing stages.

3. **Introduce semaphores for concurrency**
   - In `consumer.py`, create a global `concurrency_semaphore` controlled by `max_concurrent_runs`.
   - In OCR/LLM stages, add `ocr_semaphore` and `llm_semaphore` based on config.

4. **Wire async processing loop**
   - Update Kafka consumer loop to process messages via async tasks guarded by `concurrency_semaphore`.
   - Ensure proper `try/finally` to release semaphores.

5. **Implement timeout wrappers**
   - For async-compatible stages, use `asyncio.wait_for` with stage timeouts.
   - For sync stages, consider running them in thread pools and bounding around them (coarse-grained timeouts).

6. **Add document size checks**
   - In pre-processing, check document size against `max_document_size_mb`.
   - Fail fast with a clear error if exceeded.

7. **Add backpressure to Kafka consumption**
   - Use semaphore capacity to decide when to pause/resume consumption or simply delay polling.

8. **Instrument metrics and logs**
   - Record per-stage durations and timeout events.
   - Log structured context (`request_id`, `run_id`, stage, error_code) on failures.

9. **Run load and stress tests in dev**
   - Simulate realistic Kafka load with different document sizes.
   - Tune concurrency and timeout settings to achieve target P95/P99.

10. **Document tuning guidelines**
   - Add a short section (in README or ops runbook) describing how to tune `max_concurrent_runs`, `max_parallel_ocr/llm`, and timeouts for each environment.
