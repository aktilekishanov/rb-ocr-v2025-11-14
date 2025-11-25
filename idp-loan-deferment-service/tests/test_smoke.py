from __future__ import annotations

from io import BytesIO
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200


def test_ready():
    resp = client.get("/ready")
    assert resp.status_code == 200


def test_process_happy_path(tmp_path: Path):
    # Create a tiny dummy PDF-like file in memory
    dummy_content = b"%PDF-1.4\n%dummy pdf file\n"
    files = {
        "file": ("sample.pdf", BytesIO(dummy_content), "application/pdf"),
    }
    data = {"fio": "Иванов Иван Иванович"}

    resp = client.post("/v1/process", files=files, data=data)
    assert resp.status_code == 200
    body = resp.json()
    assert "run_id" in body and isinstance(body["run_id"], str)
    assert "verdict" in body
    assert "errors" in body


def test_process_rejects_unsupported_extension():
    dummy_content = b"fake binary"
    files = {
        "file": ("sample.txt", BytesIO(dummy_content), "text/plain"),
    }
    data = {"fio": "Иванов Иван Иванович"}

    resp = client.post("/v1/process", files=files, data=data)
    assert resp.status_code == 400
    body = resp.json()
    detail = body.get("detail")
    assert isinstance(detail, dict)
    assert detail.get("code") == "UNSUPPORTED_FILE_TYPE"
    assert "Unsupported file type" in detail.get("message", "")
