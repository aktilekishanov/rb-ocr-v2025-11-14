from __future__ import annotations

import asyncio
import os
import threading
import uuid
from pathlib import Path
from typing import Any

from fastapi import BackgroundTasks

from app.core.config import get_settings
from app.core.logging import get_logger
from app.application.services.pipeline_runner import run_sync_pipeline_app
from app.services.storage.local_disk import LocalStorage
from app.observability.metrics import (
    inc_job_submitted,
    inc_job_completed,
    inc_job_failed,
)


_logger = get_logger(__name__)
_lock = threading.Lock()
_jobs: dict[str, dict[str, Any]] = {}


def _storage() -> LocalStorage:
    settings = get_settings()
    return LocalStorage(settings.RUNS_DIR)


def _write_job_json(run_id: str, payload: dict[str, Any]) -> None:
    try:
        _storage().write_json(run_id, "meta/job.json", payload)
    except Exception as e:
        _logger.error("job_json_write_failed", extra={"run_id": run_id, "error": str(e)})


def create_job_record(run_id: str) -> None:
    with _lock:
        _jobs[run_id] = {"status": "accepted", "verdict": None, "errors": None}
    _write_job_json(run_id, {"run_id": run_id, "status": "accepted", "verdict": None, "errors": None})


def set_running(run_id: str) -> None:
    with _lock:
        rec = _jobs.get(run_id)
        if rec is None:
            rec = {"status": "running", "verdict": None, "errors": None}
            _jobs[run_id] = rec
        rec.update({"status": "running", "verdict": None, "errors": None})
    _write_job_json(run_id, {"run_id": run_id, "status": "running", "verdict": None, "errors": None})


def set_completed(run_id: str, *, verdict: bool, errors: list[str]) -> None:
    with _lock:
        rec = _jobs.get(run_id) or {}
        rec.update({"status": "completed", "verdict": bool(verdict), "errors": list(errors)})
        _jobs[run_id] = rec
    _write_job_json(run_id, {"run_id": run_id, "status": "completed", "verdict": bool(verdict), "errors": list(errors)})
    try:
        inc_job_completed()
    except Exception:
        pass


def set_failed(run_id: str, *, error: str | None = None) -> None:
    err_list = [error] if error else []
    with _lock:
        rec = _jobs.get(run_id) or {}
        rec.update({"status": "failed", "verdict": None, "errors": err_list})
        _jobs[run_id] = rec
    _write_job_json(run_id, {"run_id": run_id, "status": "failed", "verdict": None, "errors": err_list})
    try:
        inc_job_failed()
    except Exception:
        pass


def get_job_status(run_id: str) -> dict[str, Any] | None:
    with _lock:
        rec = _jobs.get(run_id)
        if rec is None:
            return None
        return {"run_id": run_id, **rec}


def process_job_sync(run_id: str, file_temp_path: str, fio: str) -> None:
    # Run the async pipeline in this background thread via a fresh event loop
    try:
        asyncio.run(_process_job_async(run_id, file_temp_path, fio))
    except Exception as e:
        # As a last resort, mark failed if something escaped
        set_failed(run_id, error=str(e)[:200])


async def _process_job_async(run_id: str, file_temp_path: str, fio: str) -> None:
    try:
        set_running(run_id)
        result = await run_sync_pipeline_app(run_id=run_id, input_path=Path(file_temp_path), meta={"fio": fio})
        verdict = bool(result.get("verdict"))
        errors = list(result.get("errors", [])) if isinstance(result.get("errors"), list) else []
        set_completed(run_id, verdict=verdict, errors=errors)
    except Exception as e:
        set_failed(run_id, error=str(e)[:200])
    finally:
        try:
            os.unlink(file_temp_path)
        except Exception:
            pass


def submit_job(background_tasks: BackgroundTasks, *, file_temp_path: str, fio: str) -> str:
    run_id = str(uuid.uuid4())
    create_job_record(run_id)
    try:
        inc_job_submitted()
    except Exception:
        pass
    background_tasks.add_task(process_job_sync, run_id, file_temp_path, fio)
    _logger.info("job_submitted", extra={"run_id": run_id})
    return run_id
