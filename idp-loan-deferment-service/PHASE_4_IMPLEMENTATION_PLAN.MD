# Phase 4 – Security Hardening: Implementation Plan

Scope: strengthen transport/application security, introduce auth, manage secrets correctly, and define PII handling/retention. This phase does not add new business logic. It ensures the service is safe to expose beyond an internal lab network.

---

## 1. Goals

- Enforce authentication on sensitive endpoints (Phase 1–3 APIs), allow health/ready to remain open (configurable).
- Prepare for TLS termination (typically at gateway/ingress); document local TLS dev option.
- Manage secrets exclusively via environment/secret store – never hardcode.
- Introduce PII redaction in logs and define data retention for artifacts in `runs/`.
- Add tests for auth gating and basic redaction/retention behavior.

---

## 2. Directory and files to create/extend

Under `apps/idp-loan-deferment-service/`:

- **New: `app/security/`**
  - `app/security/__init__.py`
  - `app/security/auth.py` – auth primitives:
    - JWT verifier (Bearer tokens) using configurable issuer/audience and JWKS or PEM.
    - Optional mTLS gate (trust proxy to pass client cert info in headers).
    - FastAPI dependency and/or middleware to enforce auth with path exemptions.
  - `app/security/permissions.py` (optional) – helpers for role/claim checks.

- **New: `app/policies/`**
  - `app/policies/__init__.py`
  - `app/policies/pii.py` – redaction helpers for logs (mask names, tokens, IDs).

- **New: `app/maintenance/`**
  - `app/maintenance/__init__.py`
  - `app/maintenance/cleanup.py` – `cleanup_old_runs(base_dir: Path, retention_days: int)` to prune old runs by directory date.

- **Extensions**
  - `app/core/config.py` – add security‑related settings (see §3).
  - `app/main.py` – register auth middleware/dependencies; optionally protect `/metrics`.
  - `app/core/logging.py` – integrate redaction helper in the structured logging formatter or at log call sites (minimal change: redact inputs before logging extras).

- **Tests**
  - `tests/test_auth.py` – 401/403 behavior, exemptions, valid JWT acceptance.
  - `tests/test_pii.py` – ensure redaction helper masks sensitive fields.
  - `tests/test_cleanup.py` – simulate `runs/` tree, verify old runs are removed.

---

## 3. Configuration (env‑driven)

Add the following to `app/core/config.py` (Pydantic Settings):

- Auth toggles
  - `AUTH_ENABLED: bool = False`
  - `AUTH_MODE: Literal["jwt", "mtls"] = "jwt"`
  - `AUTH_EXEMPT_PATHS: list[str]` – default: `/health`, `/ready`, `/metrics`, `/openapi.json`, `/docs`, `/docs/oauth2-redirect`

- JWT settings (used when `AUTH_MODE=jwt`)
  - `JWT_ISSUER: str | None`
  - `JWT_AUDIENCE: str | None`
  - `JWT_JWKS_URL: str | None` – recommended for rotating keys
  - `JWT_PUBLIC_KEY_PEM: str | None` – fallback when JWKS is unavailable
  - `JWT_ALGORITHMS: list[str] = ["RS256"]`
  - `JWT_CLOCK_SKEW_SECONDS: int = 60`

- mTLS settings (used when `AUTH_MODE=mtls`)
  - `MTLS_SUBJECT_WHITELIST: list[str] = []` – acceptable subject DNs (passed by gateway header)
  - `MTLS_HEADER_SUBJECT: str = "X-Client-Cert-Subject"`

- Secrets
  - All above values must come from env/secret manager only. No secrets in repo.

- PII and retention
  - `LOG_REDACTION_ENABLED: bool = True`
  - `RUNS_RETENTION_DAYS: int = 14`

Note: Keep existing settings (e.g., `RUNS_DIR`, `TRACING_ENABLED`).

---

## 4. Authentication design

- Approach: **defense at the edge** + **app‑level checks**.
  - Prefer TLS termination and mTLS at the gateway/ingress (Nginx/Ingress Controller/API Gateway). App trusts specific headers for client identity only if configured.
  - At app level, enforce JWT or mTLS checks using middleware/dependency.

- JWT mode
  - Parse `Authorization: Bearer <token>`.
  - Validate signature & claims using JWKS (preferred) or PEM key.
  - Required claims: `iss`, `aud`, `exp`, optionally `sub`, `scope`/`roles`.
  - Cache JWKS for a short time to reduce network overhead.
  - Deny with 401 on missing/invalid token, 403 on insufficient claims.

- mTLS mode
  - Trust the reverse proxy to pass `X-Client-Cert-Subject` (configurable).
  - Match subject DN against `MTLS_SUBJECT_WHITELIST`.
  - Deny with 401/403 when header missing or not whitelisted.

- Exemptions
  - Do not require auth for `/health`, `/ready`, and optionally `/metrics`.
  - Make exemptions configurable via `AUTH_EXEMPT_PATHS`.

Implementation:
- `app/security/auth.py`
  - `verify_jwt(token: str, settings) -> dict` – returns claims or raises.
  - `verify_mtls(request: Request, settings) -> None` – raises on failure.
  - `AuthMiddleware` or `require_auth` dependency which:
    - Skips exempt paths.
    - Switches by mode and enforces.

---

## 5. Secrets management

- Strict rule: All secrets/keys/issuers/audiences come from env/secret store.
- Avoid printing secrets in logs. If configuration is logged, mask values (e.g., show last 4 chars).
- For local dev, allow PEM values via env variables; production should use JWKS.

---

## 6. PII handling & logging redaction

- Never log raw file contents or large chunks of user input.
- Mask personally identifiable fields (e.g., names, IDs) when included in logs.
- `app/policies/pii.py` redaction helpers:
  - `redact_name(value: str) -> str` (e.g., keep initials)
  - `redact_generic(value: str) -> str` (mask all but last 4)
  - `redact_dict(payload: dict, keys: set[str]) -> dict` (apply per key)
- Integrate: before logging request extras (e.g., `fio`), apply redaction when `LOG_REDACTION_ENABLED`.

---

## 7. Artifact retention (runs cleanup)

- `app/maintenance/cleanup.py`:
  - `cleanup_old_runs(base_dir: Path, retention_days: int)`: delete run directories older than retention.
  - Safety: only delete directories matching `YYYY-MM-DD/` pattern and containing UUID subfolders.
- Wiring options:
  - A small background task that runs daily.
  - Or provide a CLI/cron entrypoint `python -m app.maintenance.cleanup` invoked externally.

---

## 8. Wiring in `app/main.py`

- Add auth enforcement:
  - Register `AuthMiddleware` early (after request‑id middleware, before routers) or apply `require_auth` as a dependency on routers.
- Keep `/health` and `/ready` open by default; `/metrics` can be left open internally or protected in prod via gateway.
- Optionally schedule cleanup on startup (non‑blocking) when `RUNS_RETENTION_DAYS > 0`.

---

## 9. Tests & manual verification

- `tests/test_auth.py`
  - With `AUTH_ENABLED=true`:
    - No token → 401 for `/v1/process` and `/v1/jobs*`.
    - Invalid token → 401/403.
    - Valid token (matching `iss`, `aud`, signature) → 200 on `/health` (always), 200 on business endpoints.
    - Exempt paths remain accessible without auth.
  - (Optional) mTLS: simulate proxy header to test whitelist.

- `tests/test_pii.py`
  - Ensure redaction functions mask names/IDs; ensure logging helpers use redaction when flag on.

- `tests/test_cleanup.py`
  - Create temp `runs/` tree with past dates; run cleanup; assert old directories removed, recent kept.

- Manual checks
  - Turn `AUTH_ENABLED` on/off and verify behavior with curl.
  - Confirm no PII leaks in logs.

---

## 10. Operational/TLS notes

- Prefer terminating TLS and enforcing mTLS at an API gateway / ingress controller. Point it to the app over localhost or service mesh.
- For local dev testing of TLS: run `uvicorn` with `--ssl-keyfile` and `--ssl-certfile`; do not use this pattern in production without a proper gateway.
- Protect `/metrics` at the gateway level (network policy or auth) if exposed outside trusted networks.

---

## 11. Rollout plan & acceptance criteria

- Rollout in a feature‑flag manner:
  - Deploy with `AUTH_ENABLED=false` → confirm no regressions.
  - Enable JWT in a dev env → validate with test tokens.
  - Optionally enable mTLS in an environment with proxy support.
- Acceptance criteria:
  - Auth enforced on non‑exempt endpoints when enabled; proper 401/403 responses.
  - No secrets in repo; values only via env.
  - Redaction applied where appropriate; no PII leaks in logs under normal ops.
  - Retention job or script removes artifacts older than `RUNS_RETENTION_DAYS`.
  - Tests pass (auth, pii, cleanup).

---

## 12. Risks and mitigations

- Misconfigured JWKS/keys → add clear startup/warn logs; fail closed when `AUTH_ENABLED=true` but config invalid.
- Over‑zealous retention → strict path checks; dry‑runs in non‑prod first.
- PII logging regressions → keep redaction centralized and covered by tests.
- Gateway/app mismatch for mTLS headers → document expected headers; add diagnostics when missing.














----------












































# Phase 4 – Security Hardening: Implementation Plan (Explained Step by Step)

Scope of this phase: **make the service safe to expose outside a lab**. We do **not** change business logic. We add **guards** around it:

- Who is allowed to call the API (auth).
- How secrets (keys, tokens) are stored.
- How we protect personal data (PII) in logs and on disk.
- How long we keep artifacts on disk.

Think of Phase 4 as putting **locks, badges, and shredders** around the system we already built.

---

## 1. Plain‑language goals

For a non‑security reader, Phase 4 wants to guarantee:

- **Only trusted callers** can use sensitive endpoints like `/v1/process` and `/v1/jobs*`.
- **Traffic is protected in transit** (usually by a gateway that does TLS and mTLS).
- **Secrets (keys, tokens, passwords)** never live in code or Git – only in env/secret store.
- **Personal data is handled carefully**:
  - We don’t accidentally dump full names, IDs, or document contents into logs.
  - We don’t keep old artifacts forever.

We also want this to be **switchable** with feature flags so we can turn auth on/off safely during rollout.

---

## 2. New modules and what they are for

All paths are under `apps/idp-loan-deferment-service/`.

### 2.1 `app/security/` – “Who is allowed in?”

**What it is:**
- A small Python package that **checks callers are allowed** to use the API.

**Files:**
- `app/security/__init__.py` – empty marker.
- `app/security/auth.py` – main auth logic.
- `app/security/permissions.py` (optional) – helpers like “does this token have role X?”.

**What it does / Why needed:**
- Reads the HTTP request, looks at headers like `Authorization: Bearer <token>` or mTLS headers from the gateway, and decides:
  - "Allow this request" or "reject with 401/403".
- Prevents random machines or users from calling `/v1/process` with real customer data.

**How it will work technically:**
- Expose a FastAPI **dependency** or **middleware**, e.g. `require_auth` or `AuthMiddleware`.
- This code will:
  1. Look at the URL path.
  2. If it is in the **exempt list** (e.g. `/health`, `/ready`), skip checks.
  3. Otherwise, choose auth mode based on settings:
     - `AUTH_MODE="jwt"` → validate a JWT access token.
     - `AUTH_MODE="mtls"` → validate client identity from mTLS header.
  4. If validation fails → raise `HTTPException(status_code=401/403)`.

### 2.2 `app/policies/` – “How do we handle personal data (PII)?”

**What it is:**
- A place for **rules about personal data**, separate from business logic.

**Files:**
- `app/policies/__init__.py`
- `app/policies/pii.py` – redaction helpers.

**What it does / Why needed:**
- Provides small functions that take strings/dicts and **hide sensitive pieces** before we log them.
- Example: instead of logging full FIO, we might log initials only.

**How it will work technically:**
- Expose helpers like:
  - `redact_name(value: str) -> str` – e.g. `"Иванов Иван Иванович" → "И*** И*** И***"`.
  - `redact_generic(value: str) -> str` – e.g. `"123456789" → "*****6789"`.
  - `redact_dict(payload: dict, keys: set[str]) -> dict` – redacts only some keys.
- In endpoints where we log user input (e.g., `fio`), we run values through these helpers **before** sending them to the logger.

### 2.3 `app/maintenance/` – “Housekeeping for runs/”

**What it is:**
- Utilities for **cleaning up old artifacts** in the `runs/` directory.

**Files:**
- `app/maintenance/__init__.py`.
- `app/maintenance/cleanup.py` – cleanup functions.

**What it does / Why needed:**
- Over time, `runs/YYYY-MM-DD/<run_id>/...` will grow.
- We need to avoid filling the disk and respect data retention policies.

**How it will work technically:**
- Implement `cleanup_old_runs(base_dir: Path, retention_days: int)`:
  - List subdirectories under `base_dir` that look like `YYYY-MM-DD`.
  - Convert the date from the folder name; compare with “today minus retention_days”.
  - Delete only directories older than that threshold **and** that match the expected structure (extra safety).
- Can be called:
  - From a small CLI (`python -m app.maintenance.cleanup`).
  - From a scheduled background task if we want automatic cleanup.

---

## 3. Configuration in `app/core/config.py` (feature flags & security settings)

We extend our Pydantic `Settings` class with **security‑related fields**. All of these are read from environment variables.

### 3.1 Auth toggles (high‑level switches)

**Fields to add:**

- `AUTH_ENABLED: bool = False`
  - **What:** master switch – do we enforce auth or not.
  - **Why:** lets us roll out auth safely; we can deploy the code with `AUTH_ENABLED=false`, then switch it on.
  - **How:** when `False`, `AuthMiddleware`/`require_auth` does nothing.

- `AUTH_MODE: Literal["jwt", "mtls"] = "jwt"`
  - **What:** which auth style we use.
  - **Why:** some environments rely on JWTs, some on mTLS + gateway.
  - **How:** `auth.py` will branch logic based on this field.

- `AUTH_EXEMPT_PATHS: list[str]`
  - **What:** list of paths we **never protect** (e.g. `/health`, `/ready`, `/metrics`, docs).
  - **Why:** so monitoring and debugging tools can reach basic endpoints without tokens.
  - **How:** middleware checks `request.url.path` against this list and skips auth.

### 3.2 JWT settings (when `AUTH_MODE="jwt"`)

**Concept:** JWT (JSON Web Token) is a signed JSON blob that says “who the caller is and what they’re allowed to do”. We **verify** it instead of keeping a session.

**Fields:**

- `JWT_ISSUER: str | None` – who issued the token.
- `JWT_AUDIENCE: str | None` – who the token is meant for (our API).
- `JWT_JWKS_URL: str | None` – URL where we can fetch public keys.
- `JWT_PUBLIC_KEY_PEM: str | None` – fallback raw key when JWKS is not available.
- `JWT_ALGORITHMS: list[str] = ["RS256"]` – which algorithms are accepted.
- `JWT_CLOCK_SKEW_SECONDS: int = 60` – how much clock difference we tolerate.

**How it works technically:**
- `verify_jwt(token, settings)` will:
  1. Decode token header to find key id (kid).
  2. Fetch JWKS (or use PEM) and pick the right key.
  3. Validate signature and claims (`iss`, `aud`, `exp`).
  4. Return claims dict on success or raise on failure.

### 3.3 mTLS settings (when `AUTH_MODE="mtls"`)

**Concept:** mTLS means **both sides present certificates**. Usually a gateway terminates TLS and passes us the client identity in a header.

**Fields:**

- `MTLS_SUBJECT_WHITELIST: list[str] = []`
  - Allowed subject DNs (distinguished names) for client certs.
- `MTLS_HEADER_SUBJECT: str = "X-Client-Cert-Subject"`
  - Header name where the gateway writes the subject.

**How it works technically:**
- `verify_mtls(request, settings)` will:
  - Read `request.headers[MTLS_HEADER_SUBJECT]`.
  - Check if it is in the whitelist.
  - Raise HTTP 401/403 if missing or unapproved.

### 3.4 PII and retention settings

- `LOG_REDACTION_ENABLED: bool = True`
  - If true, we automatically redact sensitive fields before logging.
- `RUNS_RETENTION_DAYS: int = 14`
  - How many days we keep run folders by default.

These are simple numbers/flags used by `pii.py` and `cleanup.py`.

---

## 4. Authentication design in more detail

### 4.1 Routing strategy (where checks happen)

- We’ll enforce auth **globally** using middleware or a shared dependency:
  - Good: no need to remember to secure each new endpoint manually.
  - We’ll still allow **exempt paths**.

### 4.2 JWT mode – step by step

1. Client sends `Authorization: Bearer <token>` header.
2. `AuthMiddleware` extracts the token string.
3. Calls `verify_jwt(token, settings)`:
   - Uses configured issuer/audience to validate `iss` and `aud` claims.
   - Uses JWKS URL or PEM to verify signature.
   - Checks expiration `exp` with a small clock skew window.
4. If validation fails, we raise `HTTPException(status_code=401 or 403)`.
5. If OK, we attach claims to `request.state.user` so handlers can see who called.

### 4.3 mTLS mode – step by step

1. Gateway terminates TLS and validates the client certificate.
2. Gateway writes the client’s subject DN into `X-Client-Cert-Subject` (or configured header).
3. `AuthMiddleware` reads that header and compares it to `MTLS_SUBJECT_WHITELIST`.
4. If not present or not in the list → reject.
5. If present → consider the request authenticated.

### 4.4 Exemptions

- Before doing anything, `AuthMiddleware` checks `request.url.path`:
  - If in `AUTH_EXEMPT_PATHS` (e.g., `/health`, `/ready`, docs), it skips checks entirely.
  - This is important so monitoring tools continue to work even if auth is misconfigured.

---

## 5. Secrets management (high‑level rules)

**What is a secret here?**
- JWT public keys (PEM), JWKS URLs (arguably), client IDs, any tokens/passwords for future integrations.

**Rules:**
- Never commit secrets to Git.
- Keep secrets in environment variables or a secret manager (Vault, KMS, etc.).
- If we log configuration, we **mask** secrets – for example, show only last 4 characters.

**How it ties into our code:**
- `app/core/config.py` already reads configuration from env; we will:
  - Add security fields there (see §3).
  - Be careful in startup logs to avoid printing full secret values.

---

## 6. PII handling & logging redaction

**What is PII here?**
- FIO (full name), document numbers, maybe account numbers given later.

**Why care?**
- Logs can end up in log systems, tickets, screenshots.
- We want logs to be helpful for debugging **without** leaking raw personal data.

**How we implement it:**

1. In `app/policies/pii.py` create helper functions (see §2.2).
2. In logging calls for request inputs (for example in `/v1/process` where we log `fio`):
   - If `settings.LOG_REDACTION_ENABLED` is true:
     - Pass values through `redact_name` / `redact_generic`.
   - Log the redacted value instead of the raw input.
3. Avoid logging file contents entirely (we already do this).

We will also add tests to make sure redaction behaves as expected and is not accidentally removed.

---

## 7. Artifact retention for `runs/`

**Problem:**
- Every processed document creates a folder in `runs/YYYY-MM-DD/<run_id>/...`.
- Over months, this can be huge, and might violate retention policies.

**Solution:**
- Implement a **cleanup job** that deletes old run folders.

**Implementation outline (`app/maintenance/cleanup.py`):**

- `cleanup_old_runs(base_dir: Path, retention_days: int) -> None`:
  1. Determine `cutoff_date = today - retention_days`.
  2. For each subdirectory of `base_dir`:
     - If name matches `YYYY-MM-DD` and date < cutoff_date:
       - Double‑check it contains only run subfolders (UUID‑shaped names).
       - Delete the directory tree.

**How we run it:**
- Option A: as a **standalone script** run by cron or a scheduler.
- Option B: as a **background task** triggered on startup, that runs daily.

We will start with Option A (simpler and safer – ops has full control).

---

## 8. Wiring in `app/main.py`

In `app/main.py` we already:
- Set up logging.
- Set up request ID middleware.
- Set up metrics middleware and routers.

For Phase 4 we will:

1. **Import and register auth**
   - Import `AuthMiddleware` or `require_auth` from `app.security.auth`.
   - If `settings.AUTH_ENABLED` is true:
     - Add the middleware right after `RequestIdMiddleware` and before routers **or** attach `require_auth` as a dependency on business routers (`/v1/*`).

2. **Leave health/ready open**
   - Make sure `/health` and `/ready` are in `AUTH_EXEMPT_PATHS` by default.

3. **Optionally schedule cleanup**
   - If we choose a background approach for cleanup:
     - Inside the lifespan startup, schedule a task that calls `cleanup_old_runs` once a day.
   - Otherwise, document how to run the CLI script.

---

## 9. Tests and manual verification

We will add **three small test modules**.

### 9.1 `tests/test_auth.py`

Goals:
- Confirm that enabling auth actually protects endpoints.
- Confirm exempt paths stay open.

Cases:
- With `AUTH_ENABLED=true` and JWT mode:
  - No token on `/v1/process` → 401.
  - Invalid token → 401/403.
  - Valid token (fake test key) → 200 on `/v1/process`.
  - `/health` and `/ready` → 200 without token.

### 9.2 `tests/test_pii.py`

Goals:
- Confirm that redaction helpers behave as expected.

Cases:
- `redact_name("Иванов Иван Иванович")` doesn’t return the raw string.
- `redact_generic("123456789")` masks the first part.
- `redact_dict` only masks specified keys.

### 9.3 `tests/test_cleanup.py`

Goals:
- Confirm that cleanup only removes correctly dated folders older than retention.

Cases:
- Build a temporary `runs` tree with fake date folders, e.g. 30 days ago vs today.
- Run `cleanup_old_runs` with `retention_days=14`.
- Assert old folder deleted, recent one remains.

**Manual checks:**
- Turn `AUTH_ENABLED` on/off in env and use `curl` to confirm behavior.
- Inspect logs to ensure FIO and other PII are redacted when the flag is on.

---

## 10. TLS and deployment notes (conceptual)

TLS itself is usually **not handled inside this app** in production – instead:

- A gateway or ingress controller:
  - Terminates TLS (HTTPS).
  - Validates client certificates (mTLS) if needed.
  - Forwards plain HTTP traffic to this service over a trusted network.

For local experiments:
- You can run `uvicorn` with `--ssl-keyfile` and `--ssl-certfile`, but this should stay a **dev‑only trick**, not a production pattern.

`/metrics`:
- In production, protect it via:
  - Network rules (only Prometheus can reach it), or
  - Auth at gateway level.

---

## 11. Rollout & acceptance criteria (security)

**Rollout plan:**
- Step 1: Deploy code with `AUTH_ENABLED=false` → confirm no regressions.
- Step 2: Turn `AUTH_ENABLED=true` in dev → test JWT/mTLS flows.
- Step 3: Promote config to higher envs once validated.

**Acceptance criteria:**
- When `AUTH_ENABLED=true`:
  - Sensitive endpoints (e.g., `/v1/process`, `/v1/jobs*`) require auth and respond with correct 401/403 on errors.
  - Exempt endpoints (`/health`, `/ready`, docs) remain accessible.
- No secrets are present in the repo; all come from env/secret store.
- When `LOG_REDACTION_ENABLED=true`, FIO and other PII are redacted in logs.
- Retention job or script deletes artifacts older than `RUNS_RETENTION_DAYS`.
- All new tests (`test_auth`, `test_pii`, `test_cleanup`) pass.

---

## 12. Risks and mitigations (plain language)

- **Risk:** Auth misconfigured (wrong JWKS URL, wrong audience).
  - *Mitigation:* clear startup warnings; when `AUTH_ENABLED=true` but config invalid, fail closed (do not allow traffic) or fail fast so it’s obvious.

- **Risk:** Cleanup deletes too much.
  - *Mitigation:* strict directory pattern checks; first run only in non‑prod; log what would be deleted (dry‑run option) before enabling in prod.

- **Risk:** PII suddenly appears in logs again due to a new log call.
  - *Mitigation:* centralize redaction helpers; add unit tests; code review rule: “never log raw user input”.

- **Risk:** Gateway and app disagree on mTLS headers.
  - *Mitigation:* document expected headers and values; add explicit warnings if header is missing when `AUTH_MODE="mtls"`.

With this plan, Phase 4 gives us a **clear, teachable path** to secure the existing service without over‑complicating local development.
