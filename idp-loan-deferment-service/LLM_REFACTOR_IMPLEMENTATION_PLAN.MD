# LLM Refactor Implementation Plan (Option B: Transport vs Adapter split)

## Objectives
- Decouple transport (HTTP to OpenAI-like completions) from use-case logic (prompts + parsing) to improve SRP, testability, and evolvability.
- Keep domain stages (`doc_type.py`, `extract.py`) unchanged; they continue calling `LLMPort`.
- Support both the bank’s completions v2 endpoint and legacy internal endpoints while we migrate.

## Current State (summary)
- `LlmHttpClient` implements `LLMPort` and mixes:
  - Transport (httpx calls, SSL, timeouts, multi-JSON parsing).
  - Use-case specifics (prompt templates and JSON parsing for doc-type + extraction).
- Tests target legacy endpoints; no dedicated tests for completions v2 path yet.

## Target Architecture
- **Transport-only client**: `CompletionsHttpClient`
  - Responsibilities: HTTP POST to the configured completions endpoint, robust parsing of text/plain responses with multiple JSON objects, extraction helpers.
  - No business prompts or schema knowledge beyond extracting the assistant message content.
- **Use-case adapter**: `LlmOpenAIAdapter(LLMPort)`
  - Responsibilities: Build prompts for doc-type and extraction, call `CompletionsHttpClient`, parse the assistant message content as strict JSON, return domain DTOs (`DocTypeResult`, `ExtractionResult`).
- **Legacy adapter**: existing `LlmHttpClient` that assumed `/doc-type` and `/extract` is no longer needed for this project and should be either deleted or kept only as dead code for reference, not used at runtime.

## Scope of Work
- Implement `CompletionsHttpClient` (transport-only).
- Implement `LlmOpenAIAdapter(LLMPort)` composing `CompletionsHttpClient`.
- Centralize prompts and parsers to dedicated modules to avoid duplication.
- Wire up selection logic in factories: choose OpenAI adapter when base URL matches `/openai/` or `/completions`.
- Expand tests to cover OpenAI-like pathway and error cases.

## Detailed Design

### 1) CompletionsHttpClient (transport-only)
- Location: `app/infrastructure/clients/completions_http.py`
- Interface (sync, mirroring current style):
  - `__init__(base_url: str, timeout_seconds: int, verify_ssl: bool = True, transport: httpx.BaseTransport | None = None)`
  - `_post_completion(payload: dict) -> dict`: POST with JSON body, return dict; if `Content-Type` is text/plain with multiple JSON objects, parse the last JSON object.
  - `complete(content: str, *, model: str, temperature: float, max_tokens: int) -> dict`: constructs PascalCase payload `{Model, Content, Temperature, MaxTokens}` and calls `_post_completion`.
  - `extract_message_content(resp: dict) -> str`: return `choices[0].message.content` if present; else fallback to `Content`.
- Behavior:
  - Strictly no prompt templates, no domain JSON parsing.
  - Add minimal retry/backoff for transient 429/5xx (configurable; can be toggled on later).
  - Pass-through headers if needed later (e.g., correlation id).

### 2) Prompts and Parsers (application-level)
- Locations:
  - `app/application/llm/prompts.py`
  - `app/application/llm/parsers.py`
- Prompts:
  - `build_doc_type_prompt(text: str) -> str`
  - `build_extract_prompt(text: str) -> str`
  - Keep outputs strictly defined; “Respond ONLY with JSON”.
- Parsers:
  - `parse_doc_type(json_str: str) -> tuple[str, float|None]` (doc_type, confidence)
  - `parse_fields(json_str: str) -> dict`
  - Validate schema and raise `RuntimeError` with actionable messages.

### 3) LlmOpenAIAdapter(LLMPort)
- Location: `app/application/llm/adapters/llm_openai_adapter.py`
- Constructor takes a `CompletionsHttpClient` and prompt defaults (model, temperature, max_tokens).
- Methods:
  - `classify_doc_type(pages_obj: OcrResult) -> DocTypeResult`
    - Join page texts with double newlines.
    - Build prompt via `prompts.build_doc_type_prompt`.
    - Call `client.complete(...)`.
    - Extract message text via `client.extract_message_content`.
    - Parse via `parsers.parse_doc_type`.
    - Return `DocTypeResult` with `raw` holding parsed JSON.
  - `extract_fields(pages_obj: OcrResult) -> ExtractionResult`
    - Same flow using extraction prompt/parser.

### 4) Legacy LlmHttpClient
- This adapter was designed for internal `/doc-type` and `/extract` endpoints.
- In this dev project, no external services depend on those endpoints; all real traffic is intended to go through the OpenAI-like completions endpoint.
- Therefore, `LlmHttpClient`'s legacy HTTP paths can be removed, or the entire class can be deleted once `LlmOpenAIAdapter` is in place and wired in factories.

### 5) Factory selection
- File: `app/application/services/factories.py`
- Logic:
  - Always treat `IDP_LLM_BASE_URL` as pointing to an OpenAI-like completions endpoint in this project.
  - Instantiate `CompletionsHttpClient` and wrap with `LlmOpenAIAdapter`.
- Keep interface `build_llm_client() -> LLMPort` unchanged.

## File/Module Changes
- Add:
  - `app/infrastructure/clients/completions_http.py`
  - `app/application/llm/prompts.py`
  - `app/application/llm/parsers.py`
  - `app/application/llm/adapters/llm_openai_adapter.py`
- Modify:
  - `app/application/services/factories.py` (selection logic)
  - `tests/test_llm_adapter.py` (expand coverage)
- Optional:
  - `tests/test_llm_openai_adapter.py` (new file focusing on OpenAI-like behavior)

## Configuration
- `.env`: already has `IDP_LLM_BASE_URL` pointing to `/openai/v1/completions/v2`.
- Add note: if dev uses self-signed certs, set `IDP_LLM_VERIFY_SSL=false` or install the CA.
- Consider `IDP_LLM_MODEL`, `IDP_LLM_TEMPERATURE`, `IDP_LLM_MAX_TOKENS` envs to tune prompts without code changes.

## Observability & Resilience
- Logging: log request correlation id and status codes at INFO; avoid logging PII page text.
- Retries: optional exponential backoff on 429/5xx (off by default or low max attempts).
- Timeouts: keep from settings; surface clear error messages.
- Metrics: count attempts, failures, latency (future).

## Testing Plan
- Unit tests (httpx MockTransport):
  - `CompletionsHttpClient`:
    - JSON response, text/plain multi-JSON response, last-object selection, malformed lines.
    - 429/5xx retry behavior (if enabled).
  - `LlmOpenAIAdapter`:
    - Happy paths for classification and extraction.
    - Non-JSON assistant message → raise.
    - Missing keys (no `doc_type`, non-dict `fields`) → raise with clear messages.
- Backward compatibility tests for legacy `LlmHttpClient` unchanged.

## Migration Steps
1. Implement `CompletionsHttpClient` with tests.
2. Implement `prompts.py` and `parsers.py` with tests.
3. Implement `LlmOpenAIAdapter(LLMPort)` with tests.
4. Update `build_llm_client()` selection logic + tests.
5. Keep existing `LlmHttpClient` for legacy; do not modify domain stages.
6. Run entire test suite; fix regressions.
7. Staged rollout in dev:
   - Set `IDP_LLM_BASE_URL` to completions v2, verify SSL config.
   - Exercise pipeline end-to-end; validate outputs.
8. Remove/retire legacy path after a stability window (separate PR).

## Backward Compatibility & Rollback
- BC: legacy adapter remains available if `LLM_BASE_URL` doesn’t match `/openai/`/`/completions`.
- Rollback: revert factory selection env or prior commit to return to legacy behavior.

## Risks & Mitigations
- Model prompts drift → Centralize in `prompts.py`, version them, and add tests.
- Non-JSON responses → Strict parsers with actionable errors; e2e monitoring in dev.
- SSL issues in dev → allow `IDP_LLM_VERIFY_SSL=false` or provide CA bundle.

## Acceptance Criteria
- Domain stages unchanged; `LLMPort` remains the only dependency.
- New adapter selected automatically for OpenAI-like URLs.
- Robust handling of text/plain multi-JSON responses.
- Comprehensive unit tests for transport and adapter paths.
- Clear errors on malformed model outputs.

## Definition of Done
- Code merged with green tests.
- `.env` updated/validated for dev.
- Documentation of selection logic and configuration options.
- Optional: deprecation note for legacy `LlmHttpClient` if we plan removal.
