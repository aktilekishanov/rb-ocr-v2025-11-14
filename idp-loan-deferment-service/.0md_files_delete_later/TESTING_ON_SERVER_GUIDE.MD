Yes, that’s a good next step, and your current service is ready for it.

### Recommended way to test on your Linux server

Since your company uses Docker, I’d do this via the container, not bare Python:

1. **Move code or image (pick one path)**

   - **Option A – Move source and build there (needs internet or internal mirror):**
     - Copy the whole [idp-loan-deferment-service/](cci:7://file:///Users/aktilekishanov/Documents/career/forte/ds/rb_ocr/2025-11-14-apps-from-server-RBOCR/apps/idp-loan-deferment-service:0:0-0:0) folder to the server.
     - On the server, from that folder:
       ```bash
       docker build -t idp-loan-deferment-service:local .
       ```
     - This only works if the server can reach a registry (Docker Hub or internal).

   - **Option B – Preferred for no‑internet server: move the image**
     - On your Mac (where Docker is working):
       ```bash
       docker save idp-loan-deferment-service:local > idp-loan-deferment-service.tar
       ```
     - Copy that `.tar` file to the Linux server (scp, etc.).
     - On the server:
       ```bash
       docker load < idp-loan-deferment-service.tar
       ```
     - Now the server has the exact same image.

2. **Run the container on the server**

   On the Linux server:

   ```bash
   docker run --rm -p 8000:8000 \
     -e IDP_LOG_LEVEL=INFO \
     -e IDP_ENV=dev \
     -v "$PWD/runs:/app/runs" \
     idp-loan-deferment-service:local
   ```

3. **Verify on the server**

   From the server (or a machine that can reach it):

   ```bash
   curl http://<server-host-or-ip>:8000/health
   curl http://<server-host-or-ip>:8000/ready
   curl -s http://<server-host-or-ip>:8000/metrics | head
   ```

If you tell me whether the Linux server has internet access to Docker Hub or only to an internal registry, I can tailor the exact copy/build procedure, but conceptually: yes, moving and testing this service on your Linux server now is the right move.






--------







The error is purely a **Docker permissions** issue, not an Nginx config issue.

### What the logs say

- As normal user:

```bash
docker images
permission denied while trying to connect to the Docker daemon socket at unix:///var/run/docker.sock
```

- As root:

```bash
sudo docker images | grep idp
idp-loan-deferment-service   local   ...
```

- When running the container **without** sudo:

```bash
docker run ... idp-loan-deferment-service:local
docker: permission denied while trying to connect to the Docker daemon socket ...
```

So:

- Docker daemon is running.
- Your **user `rb_admin2` is not allowed to talk to Docker** ([/var/run/docker.sock](cci:7://file:///var/run/docker.sock:0:0-0:0)).
- When you add `sudo` to `docker images`, it works (because root can).

### Is Nginx config related?

No.

- Files under `etc/nginx/sites-enabled` control **HTTP routing and TLS**.
- They have **nothing to do** with your user’s ability to talk to the Docker daemon socket.
- You do **not** need to change Nginx to fix `permission denied while trying to connect to the Docker daemon socket`.

### How to run the container now

For now, just run Docker commands with `sudo` on that server:

```bash
cd ~/apps/idp-loan-deferment-service
sudo mkdir -p runs

sudo docker run --rm -p 8000:8000 \
  -e IDP_LOG_LEVEL=INFO \
  -e IDP_ENV=dev \
  -v "$PWD/runs:/app/runs" \
  idp-loan-deferment-service:local
```

Then test from the server:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/ready
```

### (Later) nicer fix

Ask your admin (or do it if allowed) to:

```bash
sudo usermod -aG docker rb_admin2
# then log out and log back in
```

After that, `rb_admin2` should be able to run `docker ...` without `sudo`.

But **bottom line**: the error is from Docker socket permissions, not from Nginx configs.









----------






Understood; if that’s the full log, then our structured logger isn’t printing the underlying exception text (only `"process_failed"` / `"job_json_write_failed"` tags). So we have to reason from symptoms and do a couple of minimal checks.

Right now we know:

- App is healthy and serving `/openapi.json` + `/docs` on 8099.
- `/v1/process` → `INTERNAL_PROCESSING_ERROR`
- `/v1/jobs`:
  - submit returns `{"run_id": ..., "status": "accepted"}`
  - status returns `JOB_NOT_FOUND`
- Logs show:
  - `process_failed` (no details printed)
  - `job_json_write_failed` (repeated)

Given that:

### 1. Likely cause for `job_json_write_failed`

`job_json_write_failed` is logged around:

```python
def _write_job_json(run_id: str, payload: dict[str, Any]) -> None:
    try:
        _storage().write_json(run_id, "meta/job.json", payload)
    except Exception as e:
        _logger.error("job_json_write_failed", extra={"run_id": run_id, "error": str(e)})
```

So something in [_storage().write_json(...)](cci:1://file:///Users/aktilekishanov/Documents/career/forte/ds/rb_ocr/2025-11-14-apps-from-server-RBOCR/apps/idp-loan-deferment-service/app/services/jobs.py:27:0-29:42) is failing. That typically means:

- `RUNS_DIR` inside the container is a path that **does not exist** or is not writable.
- Or your `runs` volume is mounted someplace else than `RUNS_DIR`.

Minimal check inside the container:

```bash
sudo docker exec -it 014f29698321 /bin/bash

# inside container:
echo $IDP_RUNS_DIR
python -c "from app.core.config import get_settings; print(get_settings().RUNS_DIR)"
ls -ld /app/runs
ls -R /app/runs
```

If `RUNS_DIR` is **not** `/app/runs`, we should set `IDP_RUNS_DIR=/app/runs` in [.env](cci:7://file:///Users/aktilekishanov/Documents/career/forte/ds/rb_ocr/2025-11-14-apps-from-server-RBOCR/apps/idp-loan-deferment-service/.env:0:0-0:0) so jobs and the domain pipeline write to the same path you mounted.

### 2. Likely cause for `INTERNAL_PROCESSING_ERROR` on `/v1/process`

Most probable candidates:

- **OCR/LLM connectivity or SSL**:
  - The server might not reach:
    - `https://dev-ocr.fortebank.com/v2`
    - `https://dl-ai-dev-app01-uv01.fortebank.com/openai/v1/completions/v2`
  - Or SSL verification fails.
- **Same RUNS_DIR/path issue** as for jobs (if metadata/final_result writes fail, the route wraps the exception and returns `INTERNAL_PROCESSING_ERROR`).

Two quick experiments:

1. In the container:

   ```bash
   curl -vk https://dev-ocr.fortebank.com/v2/health || echo "OCR unreachable"
   curl -vk https://dl-ai-dev-app01-uv01.fortebank.com/openai/v1/completions/v2 || echo "LLM unreachable"
   ```

   That will show if there’s a network/SSL problem.

2. Temporarily relax SSL in [.env](cci:7://file:///Users/aktilekishanov/Documents/career/forte/ds/rb_ocr/2025-11-14-apps-from-server-RBOCR/apps/idp-loan-deferment-service/.env:0:0-0:0) to see if that’s it:

   ```env
   IDP_OCR_VERIFY_SSL=false
   IDP_LLM_VERIFY_SSL=false
   ```

   Then restart the container and test `/v1/process` again.

### 3. Next small step (no big code changes)

I’d suggest:

1. Set `IDP_RUNS_DIR=/app/runs` in your server [.env](cci:7://file:///Users/aktilekishanov/Documents/career/forte/ds/rb_ocr/2025-11-14-apps-from-server-RBOCR/apps/idp-loan-deferment-service/.env:0:0-0:0), restart the container, and retest `/v1/jobs` and `/v1/process`.
2. If errors persist, run the quick `curl` checks to OCR/LLM from inside the container.

If you paste:

- The output of `python -c "from app.core.config import get_settings; print(get_settings().RUNS_DIR)"` in the container, and  
- Any curl errors to the OCR/LLM URLs,

we can pinpoint whether it’s a runs-dir mismatch or an external service connectivity/SSL issue.