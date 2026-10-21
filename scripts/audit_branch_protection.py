"""Fail-closed audit for the main branch protection settings returned by GitHub."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

SCHEMA = "saqa.branch-protection-audit.v1"
POLICY_SCHEMA = "saqa.branch-protection-policy.v1"


def _load_json(path: Path, label: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError(f"cannot read {label}: {exc}") from exc


def audit(protection: Any, policy: Any) -> dict[str, Any]:
    """Return FAIL unless required checks and branch safety settings are explicit."""
    if not isinstance(policy, dict) or policy.get("schema") != POLICY_SCHEMA:
        raise ValueError("unsupported branch-protection policy schema")
    branch = policy.get("branch")
    required_contexts = policy.get("required_check_contexts")
    app_id = policy.get("required_check_app_id")
    if not isinstance(branch, str) or not branch.strip():
        raise ValueError("policy branch must be a non-empty string")
    if not isinstance(required_contexts, list) or not required_contexts:
        raise ValueError("policy required_check_contexts must be a non-empty array")
    if any(not isinstance(item, str) or not item.strip() for item in required_contexts):
        raise ValueError("policy required check contexts must be non-empty strings")
    if len(required_contexts) != len(set(required_contexts)):
        raise ValueError("policy required check contexts must be unique")
    if isinstance(app_id, bool) or not isinstance(app_id, int) or app_id <= 0:
        raise ValueError("policy required_check_app_id must be a positive integer")
    if not isinstance(protection, dict):
        return {
            "schema": SCHEMA, "status": "FAIL", "ready": False, "branch": branch,
            "failures": ["branch protection response must be a JSON object"],
        }

    failures: list[str] = []
    warnings: list[str] = []
    checks = protection.get("required_status_checks")
    if not isinstance(checks, dict):
        failures.append("required_status_checks is missing; required checks are not configured")
        strict = False
        configured_contexts: set[str] = set()
        app_binding: dict[str, int | None] = {}
    else:
        strict = checks.get("strict") is True
        if policy.get("require_strict_status_checks", True) and not strict:
            failures.append("required_status_checks.strict must be true")
        contexts = checks.get("contexts", [])
        bound_checks = checks.get("checks", [])
        if (
            not isinstance(contexts, list)
            or any(not isinstance(item, str) or not item.strip() for item in contexts)
        ):
            failures.append("required_status_checks.contexts must be an array of non-empty strings")
            contexts = []
        elif len(contexts) != len(set(contexts)):
            failures.append("required_status_checks.contexts must not contain duplicates")
        if not isinstance(bound_checks, list) or any(not isinstance(item, dict) for item in bound_checks):
            failures.append("required_status_checks.checks must be an array of objects")
            bound_checks = []
        configured_contexts = set(contexts)
        app_binding = {}
        seen_bound_contexts: set[str] = set()
        for index, check in enumerate(bound_checks):
            context = check.get("context")
            if not isinstance(context, str) or not context.strip():
                failures.append(f"required_status_checks.checks[{index}].context is invalid")
                continue
            if context in seen_bound_contexts:
                failures.append(f"required_status_checks.checks contains duplicate context: {context}")
                continue
            seen_bound_contexts.add(context)
            configured_contexts.add(context)
            raw_app_id = check.get("app_id")
            if raw_app_id is None:
                app_binding[context] = None
            elif isinstance(raw_app_id, bool) or not isinstance(raw_app_id, int):
                failures.append(f"required check app_id is invalid for {context}")
            else:
                app_binding[context] = raw_app_id

    missing = sorted(set(required_contexts) - configured_contexts)
    if missing:
        failures.append("required check contexts are missing: " + ", ".join(missing))
    unbound = sorted(
        context for context in required_contexts
        if context in configured_contexts and app_binding.get(context) != app_id
    )
    if unbound:
        failures.append(
            f"required checks must be bound to GitHub Actions app ID {app_id}: " + ", ".join(unbound)
        )

    for key, expected in (("allow_force_pushes", False), ("allow_deletions", False)):
        record = protection.get(key)
        if not isinstance(record, dict) or not isinstance(record.get("enabled"), bool):
            failures.append(f"{key}.enabled is missing or invalid")
        elif record["enabled"] != expected:
            failures.append(f"{key}.enabled must be {str(expected).lower()}")
    admins = protection.get("enforce_admins")
    if isinstance(admins, dict) and admins.get("enabled") is not True:
        warnings.append("enforce_admins is not enabled; administrators may be able to bypass protection")
    elif not isinstance(admins, dict):
        warnings.append("administrator enforcement could not be verified from the response")

    return {
        "schema": SCHEMA,
        "status": "PASS" if not failures else "FAIL",
        "ready": not failures,
        "branch": branch,
        "strict_status_checks": strict,
        "required_check_app_id": app_id,
        "required_check_count": len(required_contexts),
        "configured_check_count": len(configured_contexts),
        "required_check_contexts": list(required_contexts),
        "missing_check_contexts": missing,
        "unbound_check_contexts": unbound,
        "force_pushes_enabled": protection.get("allow_force_pushes", {}).get("enabled")
            if isinstance(protection.get("allow_force_pushes"), dict) else None,
        "deletions_enabled": protection.get("allow_deletions", {}).get("enabled")
            if isinstance(protection.get("allow_deletions"), dict) else None,
        "warnings": warnings,
        "failures": failures,
        "note": "This audit reports settings only. It does not change branch protection or prove that a push/merge path cannot bypass repository policy.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="GitHub branch-protection JSON response")
    parser.add_argument("--policy", type=Path, default=Path("security/branch-protection-policy.json"))
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        report = audit(_load_json(args.input, "branch protection JSON"), _load_json(args.policy, "policy JSON"))
    except ValueError as exc:
        report = {"schema": SCHEMA, "status": "UNVERIFIED", "ready": False, "failures": [str(exc)]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, sort_keys=True, indent=2))
    if report["status"] == "PASS":
        return 0
    return 1 if report["status"] == "FAIL" else 2


if __name__ == "__main__":
    raise SystemExit(main())
