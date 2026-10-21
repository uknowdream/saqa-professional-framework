"""Capture retry-aware, per-attempt pytest outcomes without storing failure text."""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any

import pytest

SHARD_SCHEMA = "saqa.test-attempt-shard.v1"
_SAFE_WORKER = re.compile(r"[^A-Za-z0-9_-]+")


def _phase_status(report: Any) -> str:
    if report.failed:
        return "FAIL"
    if report.skipped:
        return "SKIP"
    return "PASS"


class AttemptTelemetryPlugin:
    def __init__(self, config: pytest.Config) -> None:
        self.config = config
        self.records: dict[tuple[str, int], dict[str, Any]] = {}

    @pytest.hookimpl(hookwrapper=True)
    def pytest_runtest_makereport(self, item: pytest.Item, call: pytest.CallInfo[Any]):
        outcome = yield
        report = outcome.get_result()
        raw_attempt = getattr(item, "execution_count", 1)
        attempt = raw_attempt if isinstance(raw_attempt, int) and not isinstance(raw_attempt, bool) and raw_attempt > 0 else 1
        key = (str(item.nodeid), attempt)
        record = self.records.setdefault(key, {
            "nodeid": str(item.nodeid),
            "attempt_index": attempt,
            "phase_statuses": {},
            "duration_seconds": 0.0,
        })
        phase = str(report.when)
        status = _phase_status(report)
        previous = record["phase_statuses"].get(phase)
        # If a hook reports a phase more than once, preserve the failure rather than masking it.
        if previous != "FAIL":
            record["phase_statuses"][phase] = status
        duration = getattr(report, "duration", 0.0)
        if isinstance(duration, (int, float)) and not isinstance(duration, bool):
            record["duration_seconds"] += max(0.0, float(duration))

    @pytest.hookimpl
    def pytest_sessionfinish(self, session: pytest.Session, exitstatus: int) -> None:
        if not self.records:
            return
        worker = _SAFE_WORKER.sub("_", os.getenv("PYTEST_XDIST_WORKER", "master")) or "worker"
        output_dir = Path(os.getenv("SAQA_ATTEMPT_TELEMETRY_DIR", "artifacts/test-attempts"))
        output_dir.mkdir(parents=True, exist_ok=True)
        attempts = []
        for _, record in sorted(self.records.items(), key=lambda pair: (pair[0][0], pair[0][1])):
            phases = record["phase_statuses"]
            if "FAIL" in phases.values():
                status = "FAIL"
            elif "SKIP" in phases.values():
                status = "SKIP"
            else:
                status = "PASS"
            attempts.append({
                **record,
                "status": status,
                "duration_seconds": round(record["duration_seconds"], 6),
            })
        payload = {
            "schema": SHARD_SCHEMA,
            "run_id": os.getenv("GITHUB_RUN_ID", "local"),
            "run_attempt": os.getenv("GITHUB_RUN_ATTEMPT", "1"),
            "commit_sha": os.getenv("GITHUB_SHA", "unknown"),
            "python_version": f"{sys.version_info.major}.{sys.version_info.minor}",
            "worker_id": worker,
            "attempts": attempts,
            "provenance_note": "Attempt outcomes are runner observations, not proof that a test is intrinsically flaky. Failure text is intentionally omitted to avoid recording secrets.",
        }
        destination = output_dir / f"attempts-{worker}.json"
        temporary = destination.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(payload, sort_keys=True, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        temporary.replace(destination)


def pytest_configure(config: pytest.Config) -> None:
    if not hasattr(config, "_saqa_attempt_telemetry_registered"):
        plugin = AttemptTelemetryPlugin(config)
        config.pluginmanager.register(plugin, "saqa-attempt-telemetry")
        setattr(config, "_saqa_attempt_telemetry_registered", True)
