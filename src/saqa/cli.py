"""Unified command-line interface for the SAQA Professional Framework."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from . import __version__
from .evidence import verify_manifest
from .target_registry import DEFAULT_TARGETS


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="saqa",
        description="SAQA Professional Framework CLI",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("version", help="Print the SAQA framework version.")

    targets_parser = subparsers.add_parser("targets", help="List registered authorized reference targets.")
    targets_parser.add_argument("--json", action="store_true", dest="as_json", help="Emit JSON output.")

    verify_parser = subparsers.add_parser(
        "verify-manifest",
        help="Verify SHA-256 integrity and schema of an evidence manifest.",
    )
    verify_parser.add_argument("path", type=Path, help="Path to the evidence manifest JSON file.")

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "version":
        print(f"saqa-professional-framework {__version__}")
        return 0

    if args.command == "targets":
        records = [
            {
                "name": target.name,
                "kind": target.kind.value,
                "deployment": target.deployment.value,
                "base_url": target.base_url,
                "authorized": target.authorized,
                "certifiable": target.certifiable,
                "tags": sorted(target.tags),
            }
            for target in DEFAULT_TARGETS
        ]
        if args.as_json:
            print(json.dumps(records, indent=2))
        else:
            for item in records:
                print(
                    f"{item['name']} ({item['kind']}/{item['deployment']}) "
                    f"{item['base_url']} certifiable={item['certifiable']}"
                )
        return 0

    if args.command == "verify-manifest":
        ok = verify_manifest(args.path)
        if ok:
            print(f"MANIFEST_VALID: {args.path}")
            return 0
        print(f"MANIFEST_INVALID: {args.path}", file=sys.stderr)
        return 1

    return 2  # pragma: no cover


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
