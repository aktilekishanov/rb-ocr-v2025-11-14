I’ll run a small set of curl tests against your running service: happy path (already working), then missing `fio`, missing `file`, and unsupported extension, all from your apps directory so paths match. Then I’ll summarize the results.
Here are the test results I just ran:

## 1. Health / readiness

- `GET /health`  
  - Command: `curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/health`  
  - Result: `200`
- `GET /ready`  
  - Command: `curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/ready`  
  - Result: `200`

Service is up and reports ready.

## 2. `/v1/process` – happy path

- Command:

  ```bash
  curl -s -X POST "http://localhost:8000/v1/process" \
    -F "file=@/Users/aktilekishanov/Documents/career/forte/ds/rb_ocr/2025-11-14-apps-from-server-RBOCR/apps/dekret-prikaz-multiple.pdf" \
    -F "fio=Иванов Иван Иванович"
  ```

- Result:

  ```json
  {"run_id":"0e061f5a-0739-4fc0-9a05-0b97dc01337f","verdict":true,"errors":[]}
  ```

So the main flow is working as designed.

## 3. Missing fields

- **Missing `fio`**:

  ```bash
  curl -s -X POST "http://localhost:8000/v1/process" \
    -F "file=@.../dekret-prikaz-multiple.pdf"
  ```

  Result:

  ```json
  {"detail":[{"type":"missing","loc":["body","fio"],"msg":"Field required","input":null}]}
  ```

- **Missing `file`**:

  ```bash
  curl -s -X POST "http://localhost:8000/v1/process" \
    -F "fio=Иванов Иван Иванович"
  ```

  Result:

  ```json
  {"detail":[{"type":"missing","loc":["body","file"],"msg":"Field required","input":null}]}
  ```

FastAPI validation behaves correctly.

## 4. Unsupported file type

- Command (using [/etc/hosts](cci:7://file:///etc/hosts:0:0-0:0) as a `.txt` file):

  ```bash
  curl -s -X POST "http://localhost:8000/v1/process" \
    -F "file=@/etc/hosts" \
    -F "fio=Иванов Иван Иванович"
  ```

- Result:

  ```json
  {"detail":"Unsupported file type. Allowed: pdf, jpg, jpeg, png"}
  ```

File-type guard works as intended.

---

From an API + behavior standpoint, Phase 1 is now well covered:

- Health/readiness OK.
- Happy path OK.
- Required fields enforced.
- File-type validation enforced.

You can safely move to the next phase (e.g., plugging in real OCR/LLM/validator, or starting Kafka/S3 design) when you’re ready.