"""Validate and normalize a native mobile evidence JSON document."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from saqa.native_mobile import validate_native_mobile_evidence


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        payload = json.loads(args.input.read_text(encoding="utf-8"))
        result = validate_native_mobile_evidence(payload)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"schema": "saqa.native-mobile-evidence.v1", "status": "UNVERIFIED", "error": str(exc)}, indent=2))
        return 2
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "platform": result["platform"], "test_count": result["test_count"]}, indent=2))
    return 1 if result["status"] == "FAIL" else (0 if result["status"] == "PASS" else 2)


if __name__ == "__main__":
    raise SystemExit(main())
