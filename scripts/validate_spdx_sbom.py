"""Validate generated SPDX JSON SBOMs and emit a digest-bound inventory record."""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path
from typing import Any

SCHEMA = "saqa.sbom-validation.v1"


def validate_spdx(payload: Any, *, source: str, digest: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("SPDX document must be a JSON object")
    version = payload.get("spdxVersion")
    if not isinstance(version, str) or not version.startswith("SPDX-2."):
        raise ValueError("spdxVersion must identify SPDX 2.x")
    if payload.get("SPDXID") != "SPDXRef-DOCUMENT":
        raise ValueError("SPDXID must be exactly SPDXRef-DOCUMENT")
    for field in ("name", "documentNamespace"):
        if not isinstance(payload.get(field), str) or not payload[field].strip():
            raise ValueError(f"{field} must be a non-empty string")
    creation = payload.get("creationInfo")
    if not isinstance(creation, dict) or not isinstance(creation.get("creators"), list) or not creation["creators"]:
        raise ValueError("creationInfo.creators must be a non-empty array")
    packages = payload.get("packages")
    if not isinstance(packages, list):
        raise ValueError("packages must be an array")
    seen = set()
    for index, package in enumerate(packages):
        if not isinstance(package, dict):
            raise ValueError(f"packages[{index}] must be an object")
        for field in ("SPDXID", "name"):
            if not isinstance(package.get(field), str) or not package[field].strip():
                raise ValueError(f"packages[{index}].{field} must be a non-empty string")
        if package["SPDXID"] in seen:
            raise ValueError(f"duplicate package SPDXID: {package['SPDXID']}")
        seen.add(package["SPDXID"])
    return {
        "schema": SCHEMA,
        "status": "PASS",
        "format": "SPDX-JSON",
        "spdx_version": version,
        "document_name": payload["name"],
        "document_namespace": payload["documentNamespace"],
        "package_count": len(packages),
        "source": source,
        "sha256": digest,
        "validation": "structural; does not prove completeness or authenticity of the scanner",
    }


def validate_file(path: Path, output: Path) -> dict[str, Any]:
    # Never delete or overwrite the input when callers alias both paths.
    if path.resolve() == output.resolve():
        raise ValueError("SBOM input and output must be different files")
    # Remove stale PASS evidence before validating a new input.
    output.unlink(missing_ok=True)
    try:
        raw = path.read_bytes()
        payload = json.loads(raw)
    except (OSError, UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError(f"cannot read SBOM JSON: {exc}") from exc
    digest = hashlib.sha256(raw).hexdigest()
    result = validate_spdx(payload, source=path.name, digest=digest)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    return result

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        result = validate_file(args.input, args.output)
    except (OSError, ValueError) as exc:
        print(json.dumps({"schema": SCHEMA, "status": "UNVERIFIED", "error": str(exc)}, indent=2))
        return 2
    print(json.dumps({"status": result["status"], "package_count": result["package_count"], "sha256": result["sha256"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
