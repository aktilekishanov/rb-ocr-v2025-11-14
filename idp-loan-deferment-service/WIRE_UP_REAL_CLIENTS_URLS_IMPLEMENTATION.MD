# Wire Up Real OCR/LLM Clients – Implementation Guide

This document explains how to configure and adapt the new FastAPI service to use the real OCR and LLM endpoints that main-dev used, including exact URLs, expected payloads, response shapes, code adjustments, and verification steps.

---

## 1) Source of truth from main-dev

From `apps/main-dev` (analyzed files shown):

- OCR (Tesseract async client)
  - File: `rb-ocr/pipeline/clients/tesseract_async_client.py`
  - Default base URL: `https://dev-ocr.fortebank.com/v2`
  - Endpoints:
    - Upload PDF: `POST {base_url}/pdf` (multipart: `file`)
      - Response JSON contains an `id` (file/job identifier)
    - Poll result: `GET {base_url}/result/{id}`
      - Response JSON fields:
        - `status`: strings like `done`, `completed`, `success`, `finished`, `ready`, or failure (`failed`, `error`)
        - `result`: may contain the actual OCR payload
  - Success detection in main-dev: treat as success when `status` is in {done, completed, success, finished, ready} OR when `result` is present.

- OCR pages normalization
  - File: `rb-ocr/pipeline/processors/filter_ocr_response.py`
  - Expected raw payload variants:
    - `{"data": {"pages": [{"page_number": <int>, "text": <str>}, ...]}}`
    - Textract-like: `{"Blocks": [..., {"BlockType": "LINE", "Page": <int>, "Text": <str>}, ...]}`
  - This is converted into a normalized `{"pages": [{"page_number", "text"}, ...]}`.

- LLM (internal OpenAI-like completions)
  - File: `rb-ocr/pipeline/clients/llm_client.py`
  - Endpoint: `https://dl-ai-dev-app01-uv01.fortebank.com/openai/v1/completions/v2`
  - Request JSON:
    ```json
    {
      "Model": "gpt-4o",
      "Content": "<prompt>",
      "Temperature": 0,
      "MaxTokens": 500
    }
    ```
  - Response JSON (OpenAI-like): contains `choices[0].message.content` or `choices[0].text` or a top-level `content`.
  - Downstream parsing uses a generic filter to extract the first JSON dict inside the text payload.
  - Prompts: built from OCR pages JSON by prompt templates in
    - `rb-ocr/pipeline/prompts/dtc/v1.prompt.txt` (doc-type)
    - `rb-ocr/pipeline/prompts/extractor/v1.prompt.txt` (extract)

---

## 2) Environment variables to enable real clients

Set both of the following for real clients (otherwise dev fakes are used):

- OCR
  - `IDP_OCR_BASE_URL` (e.g., `https://dev-ocr.fortebank.com/v2`)
  - `IDP_OCR_TIMEOUT_SECONDS` (default: `60`)
  - `IDP_OCR_VERIFY_SSL` (`true|false`) – set `false` only if dev certs are self-signed.

- LLM
  - `IDP_LLM_BASE_URL` (e.g., `https://dl-ai-dev-app01-uv01.fortebank.com/openai/v1/completions/v2`)
  - `IDP_LLM_TIMEOUT_SECONDS` (default: `60`)
  - `IDP_LLM_VERIFY_SSL` (`true|false`)

Examples:

```bash
export IDP_OCR_BASE_URL="https://dev-ocr.fortebank.com/v2"
export IDP_OCR_TIMEOUT_SECONDS=60
export IDP_OCR_VERIFY_SSL=true

export IDP_LLM_BASE_URL="https://dl-ai-dev-app01-uv01.fortebank.com/openai/v1/completions/v2"
export IDP_LLM_TIMEOUT_SECONDS=60
export IDP_LLM_VERIFY_SSL=true
```

Docker run example:

```bash
docker run \
  -e IDP_OCR_BASE_URL="https://dev-ocr.fortebank.com/v2" \
  -e IDP_OCR_TIMEOUT_SECONDS=60 \
  -e IDP_OCR_VERIFY_SSL=true \
  -e IDP_LLM_BASE_URL="https://dl-ai-dev-app01-uv01.fortebank.com/openai/v1/completions/v2" \
  -e IDP_LLM_TIMEOUT_SECONDS=60 \
  -e IDP_LLM_VERIFY_SSL=true \
  -p 8000:8000 \
  idp-loan-deferment-service
```

---

## 3) Adapter updates required to match main-dev contracts

Our current adapters assume:
- OCR: `POST /upload` returns `{job_id}` and `GET /result/{job_id}` returns `{status, pages}`.
- LLM: `POST /doc-type` and `POST /extract` with `{pages: [...]}`.

Main-dev uses:
- OCR: `POST /pdf` returns `{id}`, `GET /result/{id}` returns `{status, result?}`.
- LLM: single completions endpoint; prompts are built per task; response contains OpenAI-like envelopes with embedded JSON in text.

Below are the changes to align with main-dev.

### 3.1 OCR adapter: `app/infrastructure/clients/ocr_http.py`

- Change upload endpoint and id field:
  - `POST {base_url}/pdf` with multipart `file`, parse `data["id"]`.
- Change success detection in `wait_result`:
  - Treat `status` in {`done`, `completed`, `success`, `finished`, `ready`} as success.
  - Also success if `result` key is present.
- Pages extraction (normalize to `OcrResult`):
  - If `result` has `data.pages`, map to `OcrPage(page_number, text)`.
  - Else if `result` has `Blocks` (Textract-like), derive per-page text lines (as in main-dev `filter_ocr_response.py`).
  - Else fallback to single empty page.

Pseudocode mapping for pages:

```python
raw = data.get("result") or {}
pages = []
if isinstance(raw.get("data"), dict) and isinstance(raw["data"].get("pages"), list):
    for p in raw["data"]["pages"]:
        pn = int(p.get("page_number")) if p.get("page_number") is not None else None
        txt = str(p.get("text") or "")
        if pn is None:  # still keep record
            pages.append(OcrPage(page_number=0, text=txt))
        else:
            pages.append(OcrPage(page_number=pn, text=txt))
elif isinstance(raw.get("Blocks"), list):
    # group TEXT/LINE by Page, join with newlines (see main-dev filter_ocr_response.py)
    ...
else:
    pages = [OcrPage(page_number=1, text="")]  # fallback
```

Keep returning `OcrResult(pages=pages, raw=data)`.

### 3.2 LLM adapter: `app/infrastructure/clients/llm_http.py`

- Replace the `/doc-type` and `/extract` endpoints with a single **completions** endpoint:
  - POST `{LLM_BASE_URL}` with JSON body:
    ```json
    {
      "Model": "gpt-4o",
      "Content": "<prompt>",
      "Temperature": 0,
      "MaxTokens": 500
    }
    ```
- Build prompts from OCR pages JSON:
  - Create prompt templates (do not import main-dev files):
    - `app/pipeline/prompts/dtc/v1.prompt.txt`
    - `app/pipeline/prompts/extractor/v1.prompt.txt`
  - Each contains a single `{}` placeholder where `json.dumps({"pages": [...]})` is injected.
- Parsing the LLM response:
  - Extract JSON from OpenAI-like envelopes: `choices[0].message.content` or `choices[0].text` or top-level `content`.
  - The content typically contains a JSON string which must be parsed into dict.
  - Convert to typed DTOs:
    - `DocTypeResult(doc_type=<str>, confidence?=<float>)`
    - `ExtractionResult(fields=<dict>)`

Pseudocode:

```python
payload = {"Model": "gpt-4o", "Content": prompt, "Temperature": 0, "MaxTokens": 500}
resp = client.post(base_url, json=payload)
obj = resp.json()
text = extract_text_from_openai_like(obj)  # message.content/text/content
inner = try_parse_first_json(text)  # main-dev filter behavior
```

Then:

- For classify_doc_type: `DocTypeResult(doc_type=inner.get("doc_type"), confidence=inner.get("confidence"))`
- For extract_fields: `ExtractionResult(fields=inner.get("fields", {}))`

---

## 4) Concrete code changes checklist

- OCR
  - [ ] `upload`: POST `/pdf`, field name `file`; parse `id`.
  - [ ] `wait_result`: success if `status` in {done, completed, success, finished, ready} or `result` present.
  - [ ] `wait_result`: normalize pages from `result.data.pages` or Textract `Blocks` to `OcrResult`.

- LLM
  - [ ] Switch base URL to completions endpoint (from env).
  - [ ] Build prompts from new templates under `app/pipeline/prompts/...`.
  - [ ] For doc-type: parse JSON from content, map to `DocTypeResult`.
  - [ ] For extract: parse JSON from content, map to `ExtractionResult`.

- Config
  - [ ] Ensure `IDP_LLM_BASE_URL` is the completions endpoint.
  - [ ] Keep SSL flags configurable.

- Use-case
  - [ ] Remove dev fallbacks once real envs are consistently configured (optional; you can keep them for dev).

- Tests
  - [ ] Update adapter tests to reflect `/pdf` and `id` for OCR.
  - [ ] Add tests that mock OpenAI-like LLM completions and ensure JSON extraction.

---

## 5) End-to-end verification steps

1. Local run with real envs

```bash
export IDP_OCR_BASE_URL="https://dev-ocr.fortebank.com/v2"
export IDP_LLM_BASE_URL="https://dl-ai-dev-app01-uv01.fortebank.com/openai/v1/completions/v2"
PYTHONPATH=. uvicorn app.main:app --reload
```

2. POST `/v1/process` with a real PDF and `fio`

- Expect HTTP 200 and body with `run_id`, `verdict`, `errors`.
- Inspect artifacts:
  - `runs/YYYY-MM-DD/<run_id>/meta/metadata.json`
  - `runs/YYYY-MM-DD/<run_id>/meta/final_result.json`

3. Async path

- `POST /v1/jobs` with PDF + `fio`, then poll `GET /v1/jobs/{run_id}` until `completed`.
- Validate `meta/job.json` and `meta/final_result.json` under the run dir.

4. LLM output sanity

- With real LLM, `fields` should be populated in `final_result.json`.
- Our validator currently checks for `fio`; you can extend rules later.

---

## 6) Troubleshooting

- SSL issues on dev endpoints
  - Set `IDP_OCR_VERIFY_SSL=false` and/or `IDP_LLM_VERIFY_SSL=false` for self-signed certs.

- OCR result structure varies
  - If `result` doesn’t contain `data.pages` or `Blocks`, capture a sample JSON and we’ll extend the normalizer accordingly.

- LLM content parsing fails
  - Save the raw content and check whether the provider returns JSON inside a string or a dict. Extend the extraction function to handle the new envelope.

- Timeouts
  - Increase `IDP_OCR_TIMEOUT_SECONDS`/`IDP_LLM_TIMEOUT_SECONDS` if services are slow.

---

## 7) Summary

- Real URLs from main-dev:
  - OCR: `https://dev-ocr.fortebank.com/v2` (POST `/pdf`, GET `/result/{id}`)
  - LLM: `https://dl-ai-dev-app01-uv01.fortebank.com/openai/v1/completions/v2` (POST completions)
- Adjust adapters to these shapes, normalize OCR pages, and parse OpenAI-like LLM responses with JSON content.
- Configure env vars and verify via `/v1/process` and `/v1/jobs`.
- If your real deployments use slightly different paths/payloads, send the actual spec/JSON and we’ll fine-tune the adapters.
