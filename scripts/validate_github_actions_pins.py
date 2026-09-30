#!/usr/bin/env python3
"""Fail-closed validator for immutable GitHub Actions references."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
USES_START = re.compile(r'^\s*(?:-\s*)?["\']?uses["\']?\s*:\s*')
PINNED_USES = re.compile(r'^\s*(?:-\s*)?["\']?uses["\']?\s*:\s*["\']?[^@\s"\']+@([0-9a-fA-F]{40})["\']?(?:\s+#.*)?\s*


def main() -> int:
    if not WORKFLOWS.is_dir():
        raise SystemExit(f"Workflow directory not found: {WORKFLOWS}")

    references = 0
    violations: list[str] = []
    for path in sorted(WORKFLOWS.glob("*.y*ml")):
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not USES_START.match(line):
                continue
            references += 1
            if not PINNED_USES.match(line):
                violations.append(f"{path.relative_to(ROOT)}:{line_number}: {line.strip()}")

    if references == 0:
        raise SystemExit("No GitHub Actions 'uses:' references found; integrity scan is invalid.")
    if violations:
        raise SystemExit("Mutable or malformed GitHub Action reference(s):\n" + "\n".join(violations))

    print(f"GITHUB_ACTION_PINNING_PASS references={references}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
)


def main() -> int:
    if not WORKFLOWS.is_dir():
        raise SystemExit(f"Workflow directory not found: {WORKFLOWS}")

    references = 0
    violations: list[str] = []
    for path in sorted(WORKFLOWS.glob("*.y*ml")):
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not USES_START.match(line):
                continue
            references += 1
            if not PINNED_USES.match(line):
                violations.append(f"{path.relative_to(ROOT)}:{line_number}: {line.strip()}")

    if references == 0:
        raise SystemExit("No GitHub Actions 'uses:' references found; integrity scan is invalid.")
    if violations:
        raise SystemExit("Mutable or malformed GitHub Action reference(s):\n" + "\n".join(violations))

    print(f"GITHUB_ACTION_PINNING_PASS references={references}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
