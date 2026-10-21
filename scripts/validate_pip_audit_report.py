"""Validate pip-audit JSON output without confusing a schema error with an audit finding."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def validate_report(value: Any) -> dict[str, int]:
    """Accept the supported pip-audit JSON root forms and validate every record."""
    if isinstance(value, list):
        dependencies = value
    elif isinstance(value, dict) and isinstance(value.get("dependencies"), list):
        dependencies = value["dependencies"]
    else:
        raise ValueError("pip-audit JSON must be a dependency array or an object with a dependencies array")

    vulnerability_count = 0
    for index, dependency in enumerate(dependencies):
        if not isinstance(dependency, dict):
            raise ValueError(f"pip-audit dependency[{index}] must be an object")
        for field in ("name", "version"):
            field_value = dependency.get(field)
            if not isinstance(field_value, str) or not field_value.strip():
                raise ValueError(f"pip-audit dependency[{index}].{field} must be a non-empty string")
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

    return {"dependency_count": len(dependencies), "vulnerability_count": vulnerability_count}


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
