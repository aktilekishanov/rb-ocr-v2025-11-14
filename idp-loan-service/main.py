import json
import mimetypes
import os
import sys
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, status
from fastapi.responses import JSONResponse

# Make main-dev pipeline importable as top-level package `pipeline` by adding its root to sys.path
_THIS_DIR = Path(__file__).resolve().parent
_PIPELINE_ROOT = (_THIS_DIR.parent / "main-dev" / "rb-ocr").resolve()
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))

# Now we can import main-dev orchestrator and settings
from pipeline.core.settings import RUNS_DIR  # type: ignore
from pipeline.orchestrator import run_pipeline  # type: ignore


class JobsStore:
    def __init__(self, runs_dir: Path) -> None:
        self._lock = threading.Lock()
        self._jobs: Dict[str, Dict[str, Any]] = {}
        self._index_path = runs_dir / "jobs_index.json"
        self._index_path.parent.mkdir(parents=True, exist_ok=True)
        # Ensure index file exists
        if not self._index_path.exists():
            try:
                self._atomic_write({})
            except Exception:
                pass

    def _read_index(self) -> Dict[str, Any]:
        try:
            with open(self._index_path, "r", encoding="utf-8") as f:
                return json.load(f) or {}
        except Exception:
            return {}

    def _atomic_write(self, obj: Dict[str, Any]) -> None:
        tmp_path = str(self._index_path) + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False)
        os.replace(tmp_path, self._index_path)

    def _update_index(self, job_id: str, payload: Dict[str, Any]) -> None:
        idx = self._read_index()
        idx[job_id] = payload
        self._atomic_write(idx)

    def add_queued(self, job_id: str, *, original_filename: str, content_type: Optional[str]) -> None:
        with self._lock:
            self._jobs[job_id] = {
                "status": "queued",
                "run_id": None,
                "final_result_path": None,
                "original_filename": original_filename,
                "content_type": content_type,
            }

    def set_running(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job:
                job["status"] = "running"

    def set_completed(self, job_id: str, *, run_id: str, final_result_path: str) -> None:
        with self._lock:
            rec = self._jobs.get(job_id) or {"status": "completed"}
            rec.update({
                "status": "completed",
                "run_id": run_id,
                "final_result_path": final_result_path,
            })
            self._jobs[job_id] = rec
            self._update_index(job_id, {
                "status": "completed",
                "run_id": run_id,
                "final_result_path": final_result_path,
            })

    def set_error(self, job_id: str) -> None:
        with self._lock:
            rec = self._jobs.get(job_id) or {"status": "error"}
            rec.update({"status": "error", "run_id": None, "final_result_path": None})
            self._jobs[job_id] = rec
            self._update_index(job_id, {"status": "error"})

    def get(self, job_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            if job_id in self._jobs:
                return dict(self._jobs[job_id])
        # If not in memory, try to recover from index for completed jobs
        idx = self._read_index()
        if job_id in idx:
            entry = dict(idx[job_id])
            return entry
        return None


app = FastAPI(title="idp-loan-service", version="0.1.0")
_executor = ThreadPoolExecutor(max_workers=2)
_runs_dir: Path = RUNS_DIR if isinstance(RUNS_DIR, Path) else Path(str(RUNS_DIR))
_store = JobsStore(_runs_dir)
_incoming_dir = (_THIS_DIR / "tmp").resolve()
_incoming_dir.mkdir(parents=True, exist_ok=True)


def _guess_content_type(filename: str, fallback: Optional[str]) -> Optional[str]:
    if fallback:
        return fallback
    mt, _ = mimetypes.guess_type(filename)
    return mt


def _worker(job_id: str, file_path: Path, fio: str, original_filename: str, content_type: Optional[str]) -> None:
    try:
        _store.set_running(job_id)
        result = run_pipeline(
            fio=fio,
            reason=None,
            doc_type="Иные документы",
            source_file_path=str(file_path),
            original_filename=original_filename,
            content_type=content_type,
            runs_root=_runs_dir,
        )
        run_id = str(result.get("run_id"))
        final_result_path = str(result.get("final_result_path"))
        if run_id and final_result_path:
            _store.set_completed(job_id, run_id=run_id, final_result_path=final_result_path)
        else:
            _store.set_error(job_id)
    except Exception:
        _store.set_error(job_id)
    finally:
        try:
            if file_path.exists():
                file_path.unlink()
        except Exception:
            pass


@app.post("/v1/jobs", status_code=status.HTTP_202_ACCEPTED)
async def create_job(file: UploadFile = File(...), fio: str = Form(...)):
    if not file:
        raise HTTPException(status_code=400, detail="file is required")
    if not fio or not isinstance(fio, str) or not fio.strip():
        raise HTTPException(status_code=400, detail="fio is required")

    job_id = str(uuid.uuid4())
    original_filename = file.filename or "upload"
    content_type = _guess_content_type(original_filename, file.content_type)

    # Save to a temporary path under service tmp dir
    suffix = os.path.splitext(original_filename)[1]
    tmp_path = (_incoming_dir / f"{job_id}{suffix}").resolve()
    try:
        with open(tmp_path, "wb") as out:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                out.write(chunk)
    except Exception:
        raise HTTPException(status_code=400, detail="failed to save upload")

    _store.add_queued(job_id, original_filename=original_filename, content_type=content_type)

    # Submit background work
    _executor.submit(_worker, job_id, tmp_path, fio.strip(), original_filename, content_type)

    return JSONResponse(status_code=status.HTTP_202_ACCEPTED, content={
        "job_id": job_id,
        "status": "queued",
    })


@app.get("/v1/jobs/{job_id}")
async def get_job(job_id: str):
    rec = _store.get(job_id)
    if not rec:
        raise HTTPException(status_code=404, detail="job not found")

    status_val = rec.get("status")
    if status_val in {"queued", "running"}:
        return {
            "job_id": job_id,
            "status": status_val,
            "verdict": None,
            "errors": [],
        }

    if status_val == "completed":
        # Prefer reading from final_result.json to align with artifacts
        fr_path = rec.get("final_result_path")
        verdict: Optional[bool] = None
        errors: list[Dict[str, Any]] = []
        try:
            if isinstance(fr_path, str) and fr_path:
                with open(fr_path, "r", encoding="utf-8") as f:
                    fr = json.load(f) or {}
                verdict = bool(fr.get("verdict")) if "verdict" in fr else None
                errs = fr.get("errors")
                if isinstance(errs, list):
                    errors = [e for e in errs if isinstance(e, dict)]
        except Exception:
            # Fall back to minimal response
            pass
        return {
            "job_id": job_id,
            "status": "completed",
            "verdict": verdict,
            "errors": errors,
        }

    if status_val == "error":
        return {
            "job_id": job_id,
            "status": "error",
            "verdict": False,
            "errors": [{"code": "INTERNAL_ERROR"}],
        }

    # Unknown status
    return {
        "job_id": job_id,
        "status": str(status_val),
        "verdict": None,
        "errors": [],
    }


# Healthcheck
@app.get("/health")
async def health():
    return {"status": "ok"}
