from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "mock_contract_service.py"


def _start(mode: str, port: int):
    env = os.environ.copy()
    env.update({"SAQA_MOCK_MODE": mode, "SAQA_MOCK_PORT": str(port)})
    process = subprocess.Popen(
        [sys.executable, str(SCRIPT)],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    for _ in range(30):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=1) as response:
                if response.status == 200:
                    return process
        except (urllib.error.URLError, ConnectionError):
            time.sleep(0.1)
    process.kill()
    raise AssertionError("mock service did not start")


def _request(port: int, path: str):
    with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=2) as response:
        return response.status, response.headers["Content-Type"], json.loads(response.read())


def test_valid_mode_matches_contract_shape():
    process = _start("valid", 3191)
    try:
        status, content_type, payload = _request(3191, "/rest/products/search?q=apple")
        assert status == 200
        assert "application/json" in content_type
        assert payload == {"data": [{"id": 1, "name": "Apple"}]}
    finally:
        process.terminate()
        process.wait(timeout=5)


def test_invalid_schema_mode_is_deterministic():
    process = _start("invalid-schema", 3192)
    try:
        status, _, payload = _request(3192, "/rest/products/search?q=apple")
        assert status == 200
        assert payload["data"][0]["id"] == "1"
    finally:
        process.terminate()
        process.wait(timeout=5)
