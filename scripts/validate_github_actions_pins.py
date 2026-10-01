#!/usr/bin/env python3
"""Fail-closed validator for immutable GitHub Actions references."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
USES_START = re.compile(r"""^\s*(?:-\s*)?["']?uses["']?\s*:\s*""")
PINNED_USES = re.compile(
    r"""^\s*(?:-\s*)?["']?uses["']?\s*:\s*["']?[^@\s"']+@([0-9a-fA-F]{40})["']?(?:\s+#.*)?\s*$"""
)
DOCKER_DIGEST = re.compile(r"^docker://[^@\s]+@sha256:[0-9a-fA-F]{64}$")


def main() -> int:
    if not WORKFLOWS.is_dir():
        raise SystemExit(f"Workflow directory not found: {WORKFLOWS}")

    references = 0
    pinnable_references = 0
    violations: list[str] = []
    for path in sorted(WORKFLOWS.glob("*.y*ml")):
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not USES_START.match(line):
                continue
            references += 1
            reference = line.split(":", 1)[1].strip().strip("'\\\"")
            display_path = path.relative_to(ROOT) if path.is_relative_to(ROOT) else path

            if reference.startswith("./"):
                continue

            if reference.startswith("docker://"):
                if not DOCKER_DIGEST.fullmatch(reference):
                    violations.append(
                        f"{display_path}:{line_number}: Docker action reference must use a full sha256 digest: {line.strip()}"
                    )
                continue

            pinnable_references += 1
            if not PINNED_USES.match(line):
                violations.append(f"{display_path}:{line_number}: {line.strip()}")

    if references == 0:
        raise SystemExit("No GitHub Actions 'uses:' references found; integrity scan is invalid.")
    if violations:
        raise SystemExit("Mutable or malformed GitHub Action reference(s):\n" + "\n".join(violations))

    print(
        "GITHUB_ACTION_PINNING_PASS "
        f"references={references} pinnable_external_references={pinnable_references}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
