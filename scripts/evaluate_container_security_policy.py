"""Apply a fail-closed policy to normalized Trivy container findings."""
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Any

POLICY_SCHEMA = "saqa.container-security-policy.v1"
SUMMARY_SCHEMA = "saqa.container-security-summary.v1"
ALLOWED_TYPES = {"vulnerability", "secret", "misconfiguration"}
ALLOWED_SEVERITIES = {"UNKNOWN", "LOW", "MEDIUM", "HIGH", "CRITICAL"}
REQUIRED_EXCEPTION_FIELDS = {"finding_type", "finding_id", "target", "reason", "owner", "ticket", "expires_on"}


def validate_policy(policy: Any, *, today: date | None = None) -> dict[str, Any]:
    if not isinstance(policy, dict) or policy.get("schema") != POLICY_SCHEMA:
        raise ValueError("unsupported container security policy schema")
    if not isinstance(policy.get("policy_id"), str) or not policy["policy_id"].strip():
        raise ValueError("policy_id must be a non-empty string")
    version = policy.get("version")
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        raise ValueError("policy version must be a positive integer")
    rules = policy.get("blocking_rules")
    if not isinstance(rules, list) or not rules:
        raise ValueError("blocking_rules must be a non-empty array")
    normalized_rules = set()
    for i, rule in enumerate(rules):
        if not isinstance(rule, dict) or not isinstance(rule.get("type"), str) or rule.get("type") not in ALLOWED_TYPES:
            raise ValueError(f"blocking_rules[{i}] has invalid type")
        severities = rule.get("severities")
        if not isinstance(severities, list) or not severities or any(not isinstance(s, str) or s not in ALLOWED_SEVERITIES for s in severities):
            raise ValueError(f"blocking_rules[{i}] has invalid severities")
        for severity in severities:
            key = (rule["type"], severity)
            if key in normalized_rules:
                raise ValueError(f"duplicate blocking rule for {key[0]} {key[1]}")
            normalized_rules.add(key)
    exceptions = policy.get("exceptions")
    if not isinstance(exceptions, list):
        raise ValueError("exceptions must be an array")
    today = today or date.today()
    seen = set()
    for i, exception in enumerate(exceptions):
        if not isinstance(exception, dict) or not REQUIRED_EXCEPTION_FIELDS.issubset(exception):
            raise ValueError(f"exceptions[{i}] is missing required fields")
        for field in REQUIRED_EXCEPTION_FIELDS:
            if not isinstance(exception[field], str) or not exception[field].strip():
                raise ValueError(f"exceptions[{i}].{field} must be a non-empty string")
        if not isinstance(exception["finding_type"], str) or exception["finding_type"] not in ALLOWED_TYPES:
            raise ValueError(f"exceptions[{i}].finding_type is invalid")
        if exception["finding_id"] in {"*", "ALL", "all"} or exception["target"] in {"*", "ALL", "all"}:
            raise ValueError("wildcard exceptions are prohibited")
        try:
            expires = date.fromisoformat(exception["expires_on"])
        except ValueError as exc:
            raise ValueError(f"exceptions[{i}].expires_on must be an ISO-8601 date") from exc
        if expires <= today:
            raise ValueError(f"exceptions[{i}] expired or expires today ({expires.isoformat()}); remove or renew with review")
        key = (exception["finding_type"], exception["finding_id"], exception["target"])
        if key in seen:
            raise ValueError(f"duplicate exception for {key}")
        seen.add(key)
    return {"rules": normalized_rules, "exceptions": exceptions, "policy_id": policy["policy_id"], "policy_version": version}


def evaluate_summary(summary: Any, policy: Any, *, today: date | None = None, report_only_expected_vulnerable_target: bool = False) -> dict[str, Any]:
    if not isinstance(summary, dict) or summary.get("schema") != SUMMARY_SCHEMA:
        raise ValueError("unsupported container security summary schema")
    findings = summary.get("findings")
    if not isinstance(findings, list):
        raise ValueError("summary findings must be an array")
    if report_only_expected_vulnerable_target and summary.get("image") != "bkimminich/juice-shop:v20.2.0":
        raise ValueError("report-only mode is restricted to the exact pinned intentionally vulnerable Juice Shop image")
    validated = validate_policy(policy, today=today)
    blocking = []
    suppressed = []
    observed = []
    exception_keys = {
        (e["finding_type"], e["finding_id"], e["target"]): e
        for e in validated["exceptions"]
    }
    for i, finding in enumerate(findings):
        if not isinstance(finding, dict):
            raise ValueError(f"findings[{i}] must be an object")
        kind, severity, finding_id, target = (
            finding.get("type"), finding.get("severity"), finding.get("id"), finding.get("target")
        )
        if not isinstance(kind, str) or kind not in ALLOWED_TYPES or not isinstance(severity, str) or severity not in ALLOWED_SEVERITIES:
            raise ValueError(f"findings[{i}] has unsupported type or severity")
        if finding_id is not None and (not isinstance(finding_id, str) or not finding_id.strip()):
            raise ValueError(f"findings[{i}].id must be a non-empty string when present")
        if target is not None and not isinstance(target, str):
            raise ValueError(f"findings[{i}].target must be a string when present")
        if (kind, severity) not in validated["rules"]:
            observed.append({"type": kind, "severity": severity, "id": finding_id, "target": target, "blocking": False})
            continue
        if not finding_id or not target:
            blocking.append({"type": kind, "severity": severity, "id": finding_id, "target": target,
                             "reason": "blocking finding lacks stable ID or target"})
            continue
        exception = exception_keys.get((kind, finding_id, target))
        record = {"type": kind, "severity": severity, "id": finding_id, "target": target}
        if exception:
            suppressed.append({**record, "exception": {
                "owner": exception["owner"], "ticket": exception["ticket"], "expires_on": exception["expires_on"]
            }})
        else:
            blocking.append({**record, "reason": "matches a blocking rule and has no active exact-match exception"})
    status = "REPORT_ONLY" if report_only_expected_vulnerable_target else ("FAIL" if blocking else "PASS")
    return {
        "schema": "saqa.container-security-policy-result.v1",
        "policy_id": validated["policy_id"],
        "policy_version": validated["policy_version"],
        "status": status,
        "release_gate_eligible": not report_only_expected_vulnerable_target,
        "finding_count": len(findings),
        "blocking_count": len(blocking),
        "suppressed_count": len(suppressed),
        "blocking_findings": blocking,
        "suppressed_findings": suppressed,
        "non_blocking_findings": observed,
        "enforcement_mode": "report-only intentionally vulnerable training target" if report_only_expected_vulnerable_target else "blocking",
        "note": ("This pinned OWASP Juice Shop image is intentionally vulnerable. Findings are preserved for scanner validation and are not a security certification." if report_only_expected_vulnerable_target else "PASS means this policy found no unsuppressed blocking findings; it is not proof of overall security."),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", required=True, type=Path)
    parser.add_argument("--policy", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--report-only-expected-vulnerable-target", action="store_true", help="record findings without release blocking; allowed only for the exact pinned OWASP Juice Shop training image")
    args = parser.parse_args(argv)
    try:
        summary = json.loads(args.summary.read_text(encoding="utf-8"))
        policy = json.loads(args.policy.read_text(encoding="utf-8"))
        result = evaluate_summary(summary, policy, report_only_expected_vulnerable_target=args.report_only_expected_vulnerable_target)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"schema": "saqa.container-security-policy-result.v1", "status": "BLOCKED", "error": str(exc)}, indent=2))
        return 2
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({key: result[key] for key in ("status", "finding_count", "blocking_count", "suppressed_count")}, indent=2))
    return 0 if result["status"] in {"PASS", "REPORT_ONLY"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
