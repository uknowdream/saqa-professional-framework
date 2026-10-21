"""Validate and normalize Trivy image-scan JSON into explicit security evidence."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SCHEMA = "saqa.container-security-summary.v1"
SEVERITIES = {"UNKNOWN", "LOW", "MEDIUM", "HIGH", "CRITICAL"}


def _list_field(result: dict[str, Any], field: str, result_index: int) -> list:
    value = result.get(field, [])
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"Results[{result_index}].{field} must be an array")
    for item_index, item in enumerate(value):
        if not isinstance(item, dict):
            raise ValueError(f"Results[{result_index}].{field}[{item_index}] must be an object")
    return value


def summarize_report(report: Any, *, image: str, scanner: str) -> dict[str, Any]:
    if not isinstance(report, dict):
        raise ValueError("Trivy report must be a JSON object")
    results = report.get("Results")
    if not isinstance(results, list):
        raise ValueError("Trivy report schema invalid: expected Results array")
    artifact_name = report.get("ArtifactName")
    if not isinstance(artifact_name, str) or not artifact_name.strip():
        raise ValueError("Trivy report must include the actual scanned ArtifactName")
    if not isinstance(image, str) or not image.strip():
        raise ValueError("image must be a non-empty string")
    if artifact_name != image:
        raise ValueError(f"requested image does not match Trivy-scanned ArtifactName: {artifact_name!r}")
    if not isinstance(scanner, str) or not scanner.strip():
        raise ValueError("scanner must be a non-empty string")
    findings = []
    for index, result in enumerate(results):
        if not isinstance(result, dict):
            raise ValueError(f"Results[{index}] must be an object")
        target = result.get("Target")
        if target is not None and not isinstance(target, str):
            raise ValueError(f"Results[{index}].Target must be a string")
        categories = (
            ("vulnerability", "Vulnerabilities", "VulnerabilityID", "FixedVersion"),
            ("secret", "Secrets", "RuleID", None),
            ("misconfiguration", "Misconfigurations", "ID", None),
        )
        for kind, field, id_field, fix_field in categories:
            for item in _list_field(result, field, index):
                severity = str(item.get("Severity") or "UNKNOWN").upper()
                if severity not in SEVERITIES:
                    raise ValueError(f"Results[{index}].{field} has unsupported severity {severity!r}")
                finding = {
                    "type": kind,
                    "target": target,
                    "id": item.get(id_field),
                    "severity": severity,
                }
                if fix_field:
                    finding["fixed_version"] = item.get(fix_field)
                if finding["id"] is not None and not isinstance(finding["id"], str):
                    raise ValueError(f"Results[{index}].{field}.{id_field} must be a string when present")
                findings.append(finding)
    counts = {severity: 0 for severity in ("CRITICAL", "HIGH", "MEDIUM", "LOW", "UNKNOWN")}
    for finding in findings:
        counts[finding["severity"]] += 1
    return {
        "schema": SCHEMA,
        "image": image,
        "scanned_artifact_name": artifact_name,
        "scanner": scanner,
        "finding_count": len(findings),
        "by_severity": counts,
        "findings": findings,
        "enforcement": "report-only pending triage; not release certification",
    }


def summarize_file(input_path: Path, output_path: Path, *, image: str, scanner: str) -> dict[str, Any]:
    try:
        report = json.loads(input_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read Trivy report: {exc}") from exc
    summary = summarize_report(report, image=image, scanner=scanner)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary


def main(argv: list[str] | None = None) -> int:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--image", required=True)
    parser.add_argument("--scanner", required=True)
    args = parser.parse_args(argv)
    try:
        result = summarize_file(args.input, args.output, image=args.image, scanner=args.scanner)
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps({"finding_count": result["finding_count"], "by_severity": result["by_severity"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
