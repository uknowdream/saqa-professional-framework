#!/usr/bin/env python3
"""Fast, dependency-light static preflight for the SAQA framework."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REQUIRED_SCOPE_FILES = (
    "README.md",
    "CONTRIBUTING.md",
    "LICENSE",
    "docs/GETTING_STARTED.md",
    "docker-compose.qa-targets.yml",
    "src/saqa/__init__.py",
    "src/saqa/api.py",
    "src/saqa/browser_smoke.py",
    "src/saqa/certification.py",
    "src/saqa/ci_evidence.py",
    "src/saqa/contracts.py",
    "src/saqa/evidence.py",
    "src/saqa/target_registry.py",
)

_PROHIBITED_TARGET_RE = re.compile(r"neocapture\.id", re.IGNORECASE)
_MUTATING_HTTP_RE = re.compile(
    r"(-X\s+|--request[=\s]+|method\s*=\s*)(POST|PUT|PATCH|DELETE)([^A-Za-z]|$)",
    re.IGNORECASE,
)


def run(name: str, command: list[str], env: dict[str, str] | None = None) -> None:
    print(f"[PREFLIGHT] {name}")
    completed = subprocess.run(command, cwd=ROOT, check=False, env=env)
    if completed.returncode != 0:
        raise SystemExit(f"PREFLIGHT_FAIL: {name} exited with {completed.returncode}")


def _iter_files(paths: tuple[str, ...]) -> list[Path]:
    files: list[Path] = []
    for rel in paths:
        target = ROOT / rel
        if target.is_file():
            files.append(target)
        elif target.is_dir():
            for child in sorted(target.rglob("*")):
                if child.is_file():
                    files.append(child)
    return files


def validate_framework_scope_python() -> None:
    """Cross-platform equivalent of scripts/validate_framework_scope.sh."""
    print("[PREFLIGHT] Framework scope and safety policy (Python)")
    for rel in REQUIRED_SCOPE_FILES:
        if not (ROOT / rel).is_file():
            raise SystemExit(f"FRAMEWORK_SCOPE_FAIL: missing required path: {rel}")

    compose_text = (ROOT / "docker-compose.qa-targets.yml").read_text(encoding="utf-8")
    checks = (
        ("127.0.0.1:3000:3000", "Juice Shop is not loopback-bound"),
        ("127.0.0.1:8080:8080", "WebGoat is not loopback-bound"),
        ("bkimminich/juice-shop:v20.2.0", "Juice Shop image/version is not pinned"),
        ("webgoat/webgoat:v2026.4", "WebGoat image/version is not pinned"),
    )
    for needle, message in checks:
        if needle not in compose_text:
            raise SystemExit(f"FRAMEWORK_SCOPE_FAIL: {message}")

    for path in _iter_files(("src", "scripts/qa_target_smoke.sh", ".github/workflows", "docker-compose.qa-targets.yml")):
        text = path.read_text(encoding="utf-8", errors="ignore")
        if _PROHIBITED_TARGET_RE.search(text):
            raise SystemExit(f"FRAMEWORK_SCOPE_FAIL: prohibited target reference detected in {path.relative_to(ROOT)}")

    for path in _iter_files(("src", "scripts/qa_target_smoke.sh", ".github/workflows")):
        text = path.read_text(encoding="utf-8", errors="ignore")
        if _MUTATING_HTTP_RE.search(text):
            raise SystemExit(f"FRAMEWORK_SCOPE_FAIL: mutating HTTP method invocation found in {path.relative_to(ROOT)}")

    print("FRAMEWORK_SCOPE_PASS")


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
    if os.name == "posix" and shutil.which("bash"):
        run("Framework scope and safety policy", ["bash", "scripts/validate_framework_scope.sh"])
    else:
        validate_framework_scope_python()
    print("SAQA_PREFLIGHT_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
