#!/usr/bin/env python3
"""Fast, dependency-light static preflight for the SAQA framework."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(name: str, command: list[str]) -> None:
    print(f"[PREFLIGHT] {name}")
    completed = subprocess.run(command, cwd=ROOT, check=False)
    if completed.returncode != 0:
        raise SystemExit(f"PREFLIGHT_FAIL: {name} exited with {completed.returncode}")


def main() -> int:
    run("Python syntax compilation", [sys.executable, "-m", "compileall", "-q", "src", "tests", "scripts"])
    run("GitHub Action immutable pinning", [sys.executable, "scripts/validate_github_actions_pins.py"])
    run("Framework scope and safety policy", ["bash", "scripts/validate_framework_scope.sh"])
    print("SAQA_PREFLIGHT_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
