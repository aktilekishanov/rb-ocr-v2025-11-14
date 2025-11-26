# RB-OCR Cheatsheet & Troubleshooting Guide

## Deployment & Updates

### Issue: UI not updating after code sync
**Symptoms**: You have pulled the latest changes to the server, but the Streamlit UI still shows the old version (e.g., removed fields are still visible).
**Cause**: The Streamlit application is running as a background systemd service (`streamlit-dev`), which loads the code into memory on start. It does not automatically hot-reload when files change on disk in this deployment mode.
**Fix**: Restart the systemd service.
```bash
sudo systemctl restart streamlit-dev
```
**Context**: Service definition is at `apps/system/streamlit-dev.service`.

---

## Maintenance

### Issue: Git repository cluttered with `__pycache__` and `.pyc` files
**Symptoms**: `git status` shows many untracked or modified `*.pyc` files, or they keep reappearing after deletion.
**Cause**: Python automatically generates bytecode cache files. If these are not ignored in `.gitignore`, they get committed or show up as untracked files.
**Fix**:
1.  Ensure `.gitignore` includes:
    ```gitignore
    __pycache__/
    *.py[cod]
    *$py.class
    ```
2.  Remove already tracked cache files from the index (without deleting them from disk, though you usually want to delete them too):
    ```bash
    git rm -r --cached .
    git add .
    git commit -m "Fix: remove tracked cache files"
    ```
