Summary of the Online Meeting
1. Purpose of the meeting
The participants aimed to clarify:
What exactly is Aktilek’s role and responsibilities in the project.
What the service should do end-to-end.
How to properly structure and present the current system, including how components start, connect, and operate.
Which tech stack/framework is appropriate for the future architecture.
Yerbol emphasized that a clear understanding of the project’s purpose is necessary before discussing technical redesigns.
2. Review of the current implementation
The team discussed how the system currently runs, including interface and workflow demonstration (Aruzhan suggested showing the interface first for clarity).
Yerbol stressed the importance of showing where the system starts, how connections are made, what triggers the processing, etc.
3. General architecture guidance from Yerbol
Yerbol proposed simplifying the service structure:
Single Entry Point
A single endpoint is sufficient for file ingestion.
Whether a user uploads a file directly or passes an S3 link, it should be processed by one unified service entrypoint.
There is no need to create separate endpoints for different internal components.
Service Behavior
The service should be designed as a full-fledged backend service, not a Jupyter-style one-off script.
It should:
Accept the file / retrieve it from S3,
Trigger processing,
And provide the output (via print/log for initial testing, and eventually via API).
Reusability & System Interaction
Unlike simple “one-shot” jobs (as in Aeroflot’s use case), this service will likely need:
Persistent interactions with other systems,
Some form of reserving context or maintaining state,
Clear integration patterns.
4. Framework and stack selection
Deciding on the right backend framework is top priority.
Yerbol highlighted that the current setup (likely notebooks, ad-hoc scripts) is unsuitable for a production service that needs reliable endpoints and integration with other systems.
The team must select a framework aligned with:
API lifecycle,
Long-term interactions,
Maintainability.
5. Next steps (Agreed Action Items)
For Aktilek
Rewatch the meeting, take notes, and rethink the architecture based on guidance.
Test a minimal prototype:
Create a sample endpoint,
Upload or pull a file from S3,
Print/log the output,
Understand the flow before a full redesign.
Draft the system architecture (diagram or document).
Schedule a follow-up session with Yerbol to review and validate the architecture draft.
For Yerbol
Ready to assist in reviewing the draft architecture.
Open to consulting further as the design evolves.
6. General sentiment
The meeting was overdue (Aktilek mentioned the need existed for 1.5 months).
Participants agreed it clarified direction.
Yerbol encouraged starting with simple steps and not overcomplicating the redesign.
The meeting ended with mutual appreciation and acknowledgment of next steps.
If you'd like, I can also prepare:
A formal project requirements document,
A diagram of the recommended architecture,
A list of candidate frameworks (FastAPI, Flask, Spring Boot, etc.),
Or a step-by-step migration plan based on what you already built.
Just tell me what you want next.



----


ANALYSIS

Yes, what we’re doing now is aligned with what the tech lead (Yerbol) asked for in that meeting.

### 1. Single entry point for processing

Meeting notes:
- “Single endpoint is sufficient for file ingestion.”
- “Whether a user uploads a file directly or passes an S3 link, it should be processed by one unified service entrypoint.”

What we’re building:
- A single **`POST /v1/process`** endpoint as the **only** sync entry point for document processing.
- It takes:
  - file upload (now),
  - metadata (`fio`, `reason`, `doc_type`),
- In future we can add an optional `s3_path` field and let the same endpoint fetch from S3 instead of file upload, still **one entry point**.

So this matches the “one unified entrypoint” guidance.

### 2. Proper backend service (not a script/notebook)

Meeting notes:
- “Service should be designed as a full-fledged backend service, not a Jupyter-style one-off script.”
- Should accept file / retrieve from S3 → trigger processing → provide output.

What we’ve done:
- New **standalone FastAPI service** under `idp-loan-deferment-service`:
  - Clear app structure (`app/`, `api/`, `core/`, `services/`, `models/`).
  - Health and readiness endpoints.
  - Environment-based config and proper logging.
- Phase 1 plan:
  - `/v1/process` endpoint.
  - Internal pipeline runner and storage layer.
  - Returns structured JSON (`run_id` as real UUID, `verdict`, `errors`), not prints from a script.

This is exactly moving from “notebook/script” to “real backend service”.

### 3. Reusability & interactions with other systems

Meeting notes:
- Need persistent interactions with other systems.
- Clear integration patterns (not just one-off jobs).

What we’re enabling:
- `run_id` as a **UUID** is a stable external identifier for other services.
- Directory layout keyed by `run_id` prepares for:
  - Future REST callbacks.
  - Kafka-based ingestion (same pipeline entry).
- Clear API contract in REPORT_3.MD and PHASE_1_IMPLEMENTATION_PLAN.MD that other teams can integrate with.

### 4. Framework choice

Meeting notes:
- Need a proper backend framework, not ad-hoc scripts.
- Must support API lifecycle, long-term interactions, maintainability.

What we chose:
- **FastAPI + uvicorn**, ASGI-based, widely used for this exact pattern.
- Clean separation of concerns:
  - `core` (config/logging),
  - `api` (endpoints),
  - `services` (pipeline, storage),
  - `models` (schemas).

This is consistent with modern best practices.

---

So overall: **yes, the current FastAPI-based design and the Phase 0/Phase 1 plans are in accordance with the tech lead’s comments**. We are:

- Moving to a proper backend service.
- Using a single entrypoint (`/v1/process`) for processing.
- Designing for future S3 and Kafka integration without changing the core contract.