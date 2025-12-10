"""
Runtime settings for the RB-OCR pipeline (main-dev).

Currently exposes the root directory for per-run artifacts, with an
environment-variable override for deployment-specific paths.
"""

from __future__ import annotations

import os
from pathlib import Path

# Runs directory
# Default to ./rb-ocr/runs relative to this settings.py location
# Allow override via env RB_IDP_RUNS_DIR
env_runs_dir = os.getenv("RB_IDP_RUNS_DIR", "").strip()
if env_runs_dir:
    RUNS_DIR = Path(env_runs_dir).resolve()
else:
    RUNS_DIR = (Path(__file__).resolve().parents[2] / "runs").resolve()
