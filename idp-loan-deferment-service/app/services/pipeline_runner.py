from __future__ import annotations

import json
import uuid
from datetime import datetime
import time
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.core.logging import get_logger
from app.services.storage.local_disk import LocalStorage
from app.observability.metrics import record_pipeline_duration


async def run_sync_pipeline(*, fio: str, source_file_path: str, run_id: str | None = None) -> dict[str, Any]:
    settings = get_settings()
    logger = get_logger(__name__)

    run_id = run_id or str(uuid.uuid4())
    storage = LocalStorage(settings.RUNS_DIR)

    t0 = time.perf_counter()
    saved_input_path = storage.save_input_file(source_file_path, run_id)

    storage.write_json(
        run_id,
        "meta/metadata.json",
        {
            "fio": fio,
            "original_path": saved_input_path,
        },
    )

    verdict = True
    errors: list[str] = []

    storage.write_json(
        run_id,
        "meta/final_result.json",
        {
            "run_id": run_id,
            "verdict": verdict,
            "errors": errors,
        },
    )

    logger.info("pipeline_completed", extra={"run_id": run_id, "verdict": verdict})
    try:
        record_pipeline_duration(time.perf_counter() - t0)
    except Exception:
        pass

    return {"run_id": run_id, "verdict": verdict, "errors": errors}
