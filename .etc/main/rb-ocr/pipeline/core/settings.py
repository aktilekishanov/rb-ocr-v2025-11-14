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
_env_runs = os.getenv("RB_IDP_RUNS_DIR", "").strip()
if _env_runs:
    RUNS_DIR = Path(_env_runs).resolve()
else:
    RUNS_DIR = (Path(__file__).resolve().parents[2] / "runs").resolve()
