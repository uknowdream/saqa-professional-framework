from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


SCRIPT = Path(__file__).parents[1] / "scripts" / "juice_shop_performance_gate.py"
spec = importlib.util.spec_from_file_location("juice_shop_performance_gate", SCRIPT)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_percentile_interpolates():
    assert module._percentile([10.0, 20.0, 30.0, 40.0, 50.0], 0.95) == pytest.approx(48.0)


def test_percentile_rejects_empty():
    with pytest.raises(ValueError, match="without observations"):
        module._percentile([], 0.95)


def test_target_guard_rejects_non_loopback():
    with pytest.raises(ValueError, match="loopback"):
        module._assert_loopback_http("https://example.test")


def test_target_guard_accepts_local_http():
    module._assert_loopback_http("http://127.0.0.1:3000")
    module._assert_loopback_http("http://localhost:3000")


def test_main_records_fail_evidence_when_p95_exceeds_budget(monkeypatch, tmp_path):
    class Response:
        status_code = 200
        headers = {"content-type": "application/json"}

    class Client:
        def __init__(self, *args, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return None
        def get(self, *args, **kwargs):
            return Response()

    monkeypatch.setattr(module, "OUTPUT", tmp_path / "performance.json")
    monkeypatch.setattr(module, "REQUESTS", 3)
    monkeypatch.setattr(module, "P95_BUDGET_MS", 0.0)
    monkeypatch.setattr(module.httpx, "Client", Client)
    monkeypatch.setattr(module.time, "perf_counter", lambda: 0.0)
    monkeypatch.setattr(module, "_percentile", lambda values, percentile: 1.0)
    with pytest.raises(SystemExit):
        module.main()
    evidence = __import__("json").loads((tmp_path / "performance.json").read_text(encoding="utf-8"))
    assert evidence["status"] == "FAIL"
    assert evidence["details"]["p95_ms"] == 1.0
