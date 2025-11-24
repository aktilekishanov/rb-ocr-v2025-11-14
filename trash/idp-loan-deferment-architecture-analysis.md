# IDP Loan Deferment – Event-Driven Integration Architecture Analysis

## 1) How the proposed architecture would work

- **Trigger (Kafka event)**: Bank publishes a message to topic `di-loan-delay.event.docs-uploaded` with fields like `request_id`, `document_type`, `s3_path`, `iin` (or `in`), `first_name`, `last_name`, `second_name`.
- **Ingestion (Kafka consumer)**: IDP microservice runs a consumer (consumer group for scalability) that deserializes JSON, validates schema, and generates internal `run_id` (UUID). Correlates with `request_id` for tracing.
- **Document fetch (MinIO/S3)**: Using S3 API against `s3-dev.fortebank.com:9443` (dev), downloads the object referenced by `s3_path` (and/or bucket `loan-statements-dev`). Handles auth, TLS, and timeouts.
- **Processing pipeline**: Headless pipeline (no UI): pre-processing → OCR (image/PDF) → LLM extraction → business validation → verdict. All steps instrumented for metrics and logs.
- **Persistence and audit**: Store structured processing metadata and final JSON (at minimum) for audit/debug. Prefer idempotent writes keyed by `(request_id, run_id)`.
- **Callback (REST)**: On completion, POST verdict to the bank’s REST endpoint (URL/method/auth TBD). Include `run_id`, `request_id`, `verdict`, `errors`, and any required fields.
- **Resilience**: At-least-once semantics with idempotency keys, retries with backoff, DLQ for poison messages, and timeouts across network calls.
- **Observability**: Structured logs, metrics (latency per stage, success/fail rates), distributed trace IDs, and correlation by `request_id`/`run_id`.

High-level flow:

```
Kafka (docs-uploaded) ─► IDP Consumer
                         ├─ Generate run_id, validate payload, correlate
                         ├─ Fetch document from MinIO/S3
                         ├─ OCR → LLM extract → validate
                         ├─ Persist results & audit
                         └─ REST callback to bank with verdict
```

## 2) What is already done (from your description)

- **MVP pipeline**: Accepts PDF/image, user FIO, runs OCR → LLM extraction → validator.
- **Output JSON**: Produces `{ run_id, verdict: true|false, errors: [] }`.
- **UI wrapper**: Streamlit-based manual runner for MVP testing.
- **Status**: Works locally as MVP; not integrated with Kafka/MinIO/REST; not productionized.

## 3) What needs to be done

- **Microservice foundation**: Headless service (e.g., Python FastAPI runner or worker) with health/readiness endpoints.
- **Kafka integration**: Consumer for `di-loan-delay.event.docs-uploaded` (schema validation, error handling, idempotency with `request_id`).
- **MinIO/S3 integration**: Secure client for `s3-dev.fortebank.com:9443`, resolve `s3_path` format, credentials, TLS certs, timeouts, and retries.
- **Pipeline hardening**: Batch/async processing, configurable OCR/LLM timeouts, memory/CPU limits, concurrency control.
- **REST callback client**: Implement POST of verdict (schema, auth, retries, idempotency key, circuit breaker).
- **Schema and contracts**: Define/confirm input event schema and callback response schema; version and validate both.
- **Idempotency & duplicates**: At-least-once Kafka means dedupe by `(request_id)` or content hash; safe reprocessing without side effects.
- **Error handling**: Retry policies per failure class, DLQ topic, compensating actions, clear error codes.
- **Security & compliance**: Secrets management, TLS (9443), request signing/OAuth if required, PII handling, audit trails, redaction in logs.
- **Observability**: Structured logging, metrics (per stage), trace IDs, correlation between `request_id` and `run_id`.
- **Packaging & deploy**: Dockerfile, CI/CD, environment configuration, resource sizing, rollout strategy.
- **Testing**: Local integration with dev Kafka/MinIO, synthetic documents, E2E tests, performance tests, chaos testing for retries.

## 4) Critical questions to clarify before implementation

- **Messaging contract**: What is the authoritative schema for `di-loan-delay.event.docs-uploaded`? Is the field name `iin` or `in`? Are there optional fields? Provide JSON Schema/Avro.
- **UUID return path**: You mention “in response we’d like to receive UUID of the process.” Kafka consumers don’t reply. Should we publish a separate “processing-started” event (topic name and schema?) or call a REST ack endpoint?
- **Callback endpoint**: Exact REST URL, method, required headers, auth (mTLS, OAuth, API key), rate limits, and timeout/SLA.
- **Callback schema**: Required/optional fields? Minimal example with versioning. Should we include extracted fields or only verdict? How to represent validation errors?
- **MinIO object addressing**: Does `s3_path` include bucket and prefix, or should we always use `loan-statements-dev`? What is the canonical path format (e.g., `s3://bucket/key` vs just `key`)?
- **Document types**: What does `document_type = 4` represent? Enumerate all supported types and any type-specific extraction/validation rules.
- **Throughput & latency**: Target TPS, P95/P99 latency budget, maximum document size, acceptable processing time for OCR/LLM.
- **Failure policy**: On transient failures (MinIO/kafka/callback), how many retries/backoff? When to DLQ vs return `verdict=false`? Should we callback on both success and failure?
- **Idempotency**: Is `request_id` globally unique and stable? Should we dedupe by `request_id` only or combine with `s3_path` hash?
- **Security**: How do we obtain MinIO creds and callback auth? TLS certificate chain for 9443? Any network whitelisting requirements?
- **PII & audit**: Requirements for storage/retention/encryption of documents and extracted PII. Masking/redaction in logs. Audit trail expectations.
- **Versioning**: How will message and callback schemas evolve? What is the deprecation policy?
- **Environments**: Dev/stage/prod endpoints (Kafka, MinIO, callback). Any cross-environment topic or bucket naming conventions?
- **Monitoring & alerts**: Which KPIs matter (success rate, doc fetch failures, OCR errors, callback failures)? Alert thresholds and channels.
- **Cost & LLM limits**: Any constraints on LLM provider, model, cost caps, or on-prem requirements (no outbound internet)?

## Minimal proposed callback payload (to validate with bank)

```json
{
  "run_id": "<uuid>",
  "request_id": 123123,
  "document_type": 4,
  "status": "completed",          // completed | failed | rejected
  "verdict": true,
  "errors": [],                    // array of { code, message }
  "extracted": {                   // optional if needed
    "fio": {"first_name": "Имя", "last_name": "Фамилия", "second_name": "Отчество"},
    "iin": "960125000000"
  },
  "timings_ms": {
    "fetch": 120,
    "ocr": 850,
    "llm": 600,
    "validate": 30
  },
  "schema_version": "1.0"
}
```

## Next steps (recommended)

- **Confirm contracts**: Lock input event schema, callback URL/auth/schema, `s3_path` format, document types, and SLAs.
- **Implement skeleton**: Kafka consumer + MinIO client + stub callback; wire basic pipeline and structured logging with correlation IDs.
- **Add resilience**: Timeouts, retries, idempotency, DLQ; secure secrets and TLS.
- **E2E in dev**: Run against dev Kafka/MinIO with synthetic docs; validate callback with the bank.
- **Harden & deploy**: Metrics/alerts, Dockerize, CI/CD, and promote to stage/prod per bank’s release process.
