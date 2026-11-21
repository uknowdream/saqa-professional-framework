from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "mock_contract_service.py"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


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
    for _ in range(100):
        if process.poll() is not None:
            stderr = process.communicate(timeout=2)[1]
            raise AssertionError(f"mock process exited before readiness check: {stderr.strip()}")
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=1) as response:
                if response.status == 200:
                    return process
        except (urllib.error.URLError, ConnectionError, TimeoutError):
            time.sleep(0.1)
    process.kill()
    stderr = process.communicate(timeout=2)[1]
    raise AssertionError(f"mock service did not start: {stderr.strip()}")


def _request(port: int, path: str):
    with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=2) as response:
        return response.status, response.headers["Content-Type"], json.loads(response.read())


def test_valid_mode_matches_contract_shape():
    port = _free_port()
    process = _start("valid", port)
    try:
        status, content_type, payload = _request(port, "/rest/products/search?q=apple")
        assert status == 200
        assert "application/json" in content_type
        assert payload == {"data": [{"id": 1, "name": "Apple"}]}
    finally:
        process.terminate()
        process.wait(timeout=5)


def test_invalid_schema_mode_is_deterministic():
    port = _free_port()
    process = _start("invalid-schema", port)
    try:
        status, _, payload = _request(port, "/rest/products/search?q=apple")
        assert status == 200
        assert payload["data"][0]["id"] == "1"
    finally:
        process.terminate()
        process.wait(timeout=5)
