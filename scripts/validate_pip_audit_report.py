"""Validate pip-audit JSON output while making skipped dependency coverage explicit."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

LOCAL_PROJECT_NAME = "saqa-professional-framework"
LOCAL_PROJECT_SKIP_PREFIX = (
    "Dependency not found on PyPI and could not be audited: "
    + LOCAL_PROJECT_NAME
    + " ("
)


def validate_report(value: Any) -> dict[str, Any]:
    """Accept supported pip-audit roots and validate every audited/skipped record."""
    if isinstance(value, list):
        dependencies = value
        root_fixes = []
    elif isinstance(value, dict) and isinstance(value.get("dependencies"), list):
        dependencies = value["dependencies"]
        root_fixes = value.get("fixes", [])
        if not isinstance(root_fixes, list):
            raise ValueError("pip-audit fixes must be an array when present")
        if any(not isinstance(fix, dict) for fix in root_fixes):
            raise ValueError("pip-audit fixes entries must be objects")

    else:
        raise ValueError("pip-audit JSON must be a dependency array or an object with a dependencies array")

    vulnerability_count = 0
    skipped_dependencies: list[dict[str, str]] = []
    for index, dependency in enumerate(dependencies):
        if not isinstance(dependency, dict):
            raise ValueError(f"pip-audit dependency[{index}] must be an object")
        name = dependency.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"pip-audit dependency[{index}].name must be a non-empty string")

        # The local project is not published on PyPI, so the scanner reports it as
        # skipped rather than as an audited third-party distribution. Allow exactly
        # that documented record, and surface it instead of hiding it in the summary.
        if "skip_reason" in dependency:
            reason = dependency.get("skip_reason")
            if (
                name != LOCAL_PROJECT_NAME
                or not isinstance(reason, str)
                or not reason.startswith(LOCAL_PROJECT_SKIP_PREFIX)
                or not reason.endswith(")")
            ):
                raise ValueError(
                    f"pip-audit dependency[{index}] contains an unreviewed skip reason; "
                    "only the checked-in local project may be skipped"
                )
            if any(item["name"] == name for item in skipped_dependencies):
                raise ValueError(f"pip-audit reports duplicate skipped local project: {name}")
            skipped_dependencies.append({"name": name, "skip_reason": reason})
            continue

        version = dependency.get("version")
        if not isinstance(version, str) or not version.strip():
            raise ValueError(f"pip-audit dependency[{index}].version must be a non-empty string")
        vulns = dependency.get("vulns")
        if not isinstance(vulns, list):
            raise ValueError(f"pip-audit dependency[{index}].vulns must be an array")
        for vuln_index, vuln in enumerate(vulns):
            if not isinstance(vuln, dict):
                raise ValueError(f"pip-audit dependency[{index}].vulns[{vuln_index}] must be an object")
            identifier = vuln.get("id")
            if not isinstance(identifier, str) or not identifier.strip():
                raise ValueError(f"pip-audit dependency[{index}].vulns[{vuln_index}].id must be a non-empty string")
            for optional_list in ("fix_versions", "aliases"):
                if optional_list in vuln:
                    items = vuln[optional_list]
                    if not isinstance(items, list) or any(not isinstance(item, str) for item in items):
                        raise ValueError(
                            f"pip-audit dependency[{index}].vulns[{vuln_index}].{optional_list} must be an array of strings"
                        )
            vulnerability_count += 1

    return {
        "dependency_count": len(dependencies),
        "audited_dependency_count": len(dependencies) - len(skipped_dependencies),
        "vulnerability_count": vulnerability_count,
        "skipped_dependency_count": len(skipped_dependencies),
        "skipped_dependencies": skipped_dependencies,
        "fix_count": len(root_fixes),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        value = json.loads(args.input.read_text(encoding="utf-8"))
        result = validate_report(value)
    except (OSError, UnicodeError, json.JSONDecodeError, RecursionError, ValueError) as exc:
        print(json.dumps({"status": "UNVERIFIED", "error": str(exc)}, indent=2))
        return 2
    print(json.dumps({"status": "PASS", **result}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
