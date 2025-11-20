# Step-by-step guide: DEV → Server [DEV] → Test [DEV] → [PROD]

Below is a practical workflow you can follow every time you make changes to this project. It’s tailored to the current structure:
- Dev app: apps/main-dev/rb-ocr/app.py
- Prod app: apps/main/rbocr/app.py
- Stamp detector paths are hardcoded to:
  - [DEV]: /home/rb_admin2/apps/main-dev/stamp-processing/...
  - [PROD]: /home/rb_admin2/apps/main/stamp-processing/...

Use this as your standard operating procedure.

## Prerequisites
- You have SSH access to:
  - Server [DEV]
  - Server [PROD]
- On servers you can use Python 3.10+ and create virtualenvs.
- Network access from servers to:
  - Dev OCR: https://dev-ocr.fortebank.com/v2
  - DMZ GPT: https://dl-ai-dev-app01-uv01.fortebank.com/openai/v1/completions/v2
- Stamp detector is already installed on servers at the paths listed above.

---

## 1) Develop locally (DEV)

- **Create a branch**
  - `git checkout -b feature/<short-name>`

- **Make changes in the correct folder**
  - For UI: [apps/main-dev/rb-ocr/app.py](cci:7://file:///Users/aktilekishanov/Documents/career/forte/ds/rb_ocr/2025-11-14-apps-from-server-RBOCR/apps/main-dev/rb-ocr/app.py:0:0-0:0)
  - For pipeline: `apps/main-dev/rb-ocr/rbidp/...`

- **Run locally**
  - Create a venv and install dependencies:
    ```bash
    python -m venv .venv && source .venv/bin/activate
    pip install --upgrade pip
    pip install streamlit httpx rapidfuzz pypdf PyPDF2 pillow pymupdf
    ```
  - Run the dev app:
    ```bash
    streamlit run apps/main-dev/rb-ocr/app.py
    ```
  - Smoke test locally with a few files:
    - Upload a sample PDF/JPG.
    - Verify result (verdict, errors).
    - Open side_by_side.json + manifest.json in UI expanders.

- **Commit & push**
  - `git add -A && git commit -m "feat: <what changed>" && git push origin feature/<short-name>`

- **Merge into dev branch (if you use one) or keep feature branch**
  - Open PR → merge into `dev` (recommended)
  - Tag an internal dev version (optional): `git tag vX.Y.Z-dev && git push --tags`

---

## 2) Deploy to server [DEV]

Choose one method.

- **Option A — Git pull on server** (preferred if repo already exists there)
  - SSH in:
    ```bash
    ssh <user>@<SERVER_DEV>
    ```
  - Go to dev app base (match stamp path layout):
    ```bash
    cd /home/rb_admin2/apps/main-dev
    ```
  - Pull latest changes from your dev branch:
    ```bash
    git fetch --all
    git checkout dev   # or your branch
    git pull
    ```
  - Ensure Python venv exists for the app:
    ```bash
    python -m venv .venv || true
    source .venv/bin/activate
    pip install --upgrade pip
    pip install streamlit httpx rapidfuzz pypdf PyPDF2 pillow pymupdf
    ```

- **Option B — rsync from local machine** (if no Git on server)
  - From your local machine:
    ```bash
    rsync -avz \
      --exclude '.venv' \
      /path/to/local/repo/apps/main-dev/ \
      <user>@<SERVER_DEV>:/home/rb_admin2/apps/main-dev/
    ```
  - Then on server, create/update venv and install deps (same as Option A).

- **Run the dev app (temporary, for testing)**
  - Inside server [DEV]:
    ```bash
    cd /home/rb_admin2/apps/main-dev
    source .venv/bin/activate
    streamlit run apps/main-dev/rb-ocr/app.py --server.port 8501 --server.address 0.0.0.0
    ```
  - If you use systemd, set it up later (see “Optional: systemd” below).

---

## 3) Test on server [DEV]

- **Smoke tests**
  - Open the Streamlit URL for server [DEV] (port or reverse-proxy address).
  - Upload 1–2 sample documents per key doc type you touched.
  - Confirm:
    - Verdict logic matches expectations.
    - Error messages look sane.
    - Stamp preview appears if available.
    - side_by_side.json and manifest.json visible in UI expanders.

- **Functional checks**
  - Check `meta/final_result.json` saved under runs/<date>/<run_id>/meta/.
  - Check timings in `manifest.json` (duration_seconds, gpt_seconds, ocr_seconds, stamp_seconds).

- **Validation checklist**
  - FIO check behaves with minor typos and transliterations.
  - Doc type classification is correct and single_doc_type is True.
  - Date validity policy applies as expected (e.g., VKK 180 days).
  - Stamp detection returns expected True/False (and preview file is copied).

- **Fixes**
  - If issues are found, repeat steps 1–2 quickly and re-test.

---

## 4) Promote to [PROD]

- **Prepare a production release**
  - Merge `dev` → [main](cci:7://file:///Users/aktilekishanov/Documents/career/forte/ds/rb_ocr/2025-11-14-apps-from-server-RBOCR/apps/main:0:0-0:0) (or merge your feature branch into [main](cci:7://file:///Users/aktilekishanov/Documents/career/forte/ds/rb_ocr/2025-11-14-apps-from-server-RBOCR/apps/main:0:0-0:0)).
  - Tag version: `git tag vX.Y.Z && git push --tags`

- **Deploy on server [PROD]**
  - SSH in:
    ```bash
    ssh <user>@<SERVER_PROD>
    cd /home/rb_admin2/apps/main
    ```
  - Backup current directory (fast safety net):
    ```bash
    tar czf backup-$(date +%Y%m%d-%H%M%S).tgz apps main || true
    ```
  - Pull latest main:
    ```bash
    git fetch --all
    git checkout main
    git pull
    ```
  - Ensure venv + install/upgrade deps:
    ```bash
    python -m venv .venv || true
    source .venv/bin/activate
    pip install --upgrade pip
    pip install streamlit httpx rapidfuzz pypdf PyPDF2 pillow pymupdf
    ```

- **Run/Restart app**
  - Temporary/manual:
    ```bash
    source .venv/bin/activate
    streamlit run apps/main/rbocr/app.py --server.port 8501 --server.address 0.0.0.0
    ```
  - Or restart systemd service if you’ve set it up.

- **Post-deploy checks**
  - Repeat quick smoke tests with a small file.
  - Verify verdicts, side_by_side, manifest timings.
  - Ensure stamp detector works (paths on PROD point to /home/rb_admin2/apps/main/stamp-processing/...).

---

## Optional: systemd services (recommended)

Create a service for persistent uptime (one per environment).

- Example unit for [DEV] (`/etc/systemd/system/rb-ocr-dev.service`):
  ```ini
  [Unit]
  Description=RB OCR DEV Streamlit
  After=network.target

  [Service]
  User=rb_admin2
  WorkingDirectory=/home/rb_admin2/apps/main-dev
  ExecStart=/home/rb_admin2/apps/main-dev/.venv/bin/streamlit run apps/main-dev/rb-ocr/app.py --server.port 8501 --server.address 0.0.0.0
  Restart=always
  Environment=PYTHONUNBUFFERED=1

  [Install]
  WantedBy=multi-user.target
  ```
- Enable and start:
  ```bash
  sudo systemctl daemon-reload
  sudo systemctl enable rb-ocr-dev
  sudo systemctl restart rb-ocr-dev
  sudo systemctl status rb-ocr-dev -n 50
  ```

Repeat with a `rb-ocr-prod.service` pointing to `/home/rb_admin2/apps/main` and [apps/main/rbocr/app.py](cci:7://file:///Users/aktilekishanov/Documents/career/forte/ds/rb_ocr/2025-11-14-apps-from-server-RBOCR/apps/main/rbocr/app.py:0:0-0:0).

---

## Rollback plan

- **Code rollback**
  - `git checkout <previous-tag-or-commit>`
  - `git pull` (if needed) and restart service.

- **Directory-level rollback (if you made a backup tgz)**
  ```bash
  systemctl stop rb-ocr-prod || true
  tar xzf backup-YYYYMMDD-HHMMSS.tgz -C /
  systemctl start rb-ocr-prod || true
  ```

- **Validate after rollback**
  - Re-run smoke tests.

---

## Quick checklists

- **Before deploying to [DEV]**
  - Changes only in `apps/main-dev/rb-ocr/*` (or shared lib files).
  - Local smoke tests pass.

- **After deploying to [DEV]**
  - Basic flows pass with sample docs.
  - `manifest.json` shows reasonable timings.
  - `*_with_boxes.jpg` present when stamp exists.

- **Before promoting to [PROD]**
  - All [DEV] tests passed.
  - Merge to [main](cci:7://file:///Users/aktilekishanov/Documents/career/forte/ds/rb_ocr/2025-11-14-apps-from-server-RBOCR/apps/main:0:0-0:0) and tag release.

- **After deploying to [PROD]**
  - Smoke test with 1–2 docs.
  - Monitor logs, verify no errors.

---

# Summary

- Develop and test locally under [apps/main-dev/rb-ocr](cci:7://file:///Users/aktilekishanov/Documents/career/forte/ds/rb_ocr/2025-11-14-apps-from-server-RBOCR/apps/main-dev/rb-ocr:0:0-0:0).
- Deploy to server [DEV] via Git pull or rsync, install deps, run and test thoroughly.
- Promote by merging into [main](cci:7://file:///Users/aktilekishanov/Documents/career/forte/ds/rb_ocr/2025-11-14-apps-from-server-RBOCR/apps/main:0:0-0:0), deploy on [PROD], install deps, run/restart service, and smoke test.
- Keep a simple rollback path (git tag or tar backup) and validate after any rollback.

If you want, I can convert this into a repo document (e.g., DEPLOYMENT_GUIDE.md) and add minimal systemd units for you.