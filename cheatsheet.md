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

###     how to install dependencies offline:

cd /home/rb_admin2/apps/fastapi-service/

# Create Python virtual environment
python3 -m venv .venv

# Activate it
source .venv/bin/activate

# Install from offline wheels
pip install --no-index --find-links /home/rb_admin2/.rb-ocr-dependencies/ -r /home/rb_admin2/.rb-ocr-dependencies/requirements.txt

###     how to verify that dependencies are installed:

# On server (make sure venv is activated):
cd /home/rb_admin2/apps/fastapi-service/
source .venv/bin/activate

# Test imports
python3 << 'EOF'
import sys
sys.path.insert(0, '.')
from pipeline.orchestrator import run_pipeline
from pipeline.core.config import MAX_PDF_PAGES
print(f"✅ Pipeline imports OK. MAX_PDF_PAGES={MAX_PDF_PAGES}")
EOF