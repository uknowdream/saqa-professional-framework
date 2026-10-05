#!/usr/bin/env python3
"""Fast, dependency-light static preflight for the SAQA framework."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(name: str, command: list[str], env: dict[str, str] | None = None) -> None:
    print(f"[PREFLIGHT] {name}")
    completed = subprocess.run(command, cwd=ROOT, check=False, env=env)
    if completed.returncode != 0:
        raise SystemExit(f"PREFLIGHT_FAIL: {name} exited with {completed.returncode}")


def main() -> int:
    for directory in ("src", "tests", "scripts"):
        path = ROOT / directory
        if not path.is_dir():
            raise SystemExit(f"PREFLIGHT_FAIL: required directory missing: {directory}")
    with tempfile.TemporaryDirectory(prefix="saqa-pycache-") as cache_dir:
        env = os.environ.copy()
        env["PYTHONPYCACHEPREFIX"] = cache_dir
        run("Python syntax compilation", [sys.executable, "-m", "compileall", "-q", "src", "tests", "scripts"], env=env)
    run("GitHub Action immutable pinning", [sys.executable, "scripts/validate_github_actions_pins.py"])
    run("Framework scope and safety policy", ["bash", "scripts/validate_framework_scope.sh"])
    print("SAQA_PREFLIGHT_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
