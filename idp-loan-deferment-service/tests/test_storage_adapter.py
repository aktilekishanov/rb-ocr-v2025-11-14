from __future__ import annotations

import json
from pathlib import Path

from app.infrastructure.storage.local_disk_adapter import LocalDiskStorageAdapter


def test_local_disk_storage_adapter_roundtrip(tmp_path: Path) -> None:
    adapter = LocalDiskStorageAdapter(base_dir=tmp_path)
    run_id = "run-123"

    # create a fake input file
    src = tmp_path / "sample.pdf"
    src.write_bytes(b"%PDF-1.4\n%")

    dest = adapter.save_input(run_id, src)
    assert dest.exists()
    assert dest.name.startswith("document")

    adapter.ensure_dirs(run_id, "meta", "output")
    payload = {"ok": True, "n": 1}
    jpath = adapter.write_json(run_id, "meta/final_result.json", payload)
    assert jpath.exists()

    read_back = adapter.read_json(run_id, "meta/final_result.json")
    assert read_back == payload
