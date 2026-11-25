"""Declarative QA API/HTTP suite runner with safety guards and tamper-evident evidence."""
from __future__ import annotations

import json
import os
import re
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.parse import urlencode, urlparse, urlunparse

from .analytics import analyze_records
from .api import (
    ApiResponse,
    assert_header,
    assert_json_fields,
    assert_json_path,
    assert_response_time,
    assert_status,
    request as http_request,
    resolve_json_path,
)
from .evidence import EvidenceRecord, utc_now, write_manifest
from .http_pool import create_pooled_requester
from .url_safety import redact_url

SAFE_HTTP_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
_TEMPLATE_RE = re.compile(r"\{\{\s*([A-Za-z0-9_:\.-]+)\s*\}\}")

_JSON_TYPE_MAP: dict[str, type | tuple[type, ...]] = {
    "str": str,
    "string": str,
    "int": int,
    "integer": int,
    "float": (int, float),
    "number": (int, float),
    "bool": bool,
    "boolean": bool,
    "list": list,
    "array": list,
    "dict": dict,
    "object": dict,
    "null": type(None),
}


@dataclass(frozen=True)
class SuiteExecutionResult:
    """Complete result of running a declarative SAQA test suite."""

    suite_name: str
    records: tuple[EvidenceRecord, ...]
    analytics: dict[str, Any]
    manifest_path: Path | None = None
    manifest_sha256: str | None = None
    summary_path: Path | None = None

    @property
    def passed(self) -> bool:
        return self.analytics["overall_status"] == "PASS"


def _interpolate_string(value: str, variables: Mapping[str, Any]) -> str:
    def _replace(match: re.Match[str]) -> str:
        token = match.group(1)
        if token.startswith("env:"):
            env_name = token[4:]
            if env_name not in os.environ:
                raise ValueError(f"missing required environment variable in suite template: {env_name}")
            return os.environ[env_name]
        if token not in variables:
            raise ValueError(f"unknown suite template variable: {token}")
        return str(variables[token])

    return _TEMPLATE_RE.sub(_replace, value)


def _interpolate_value(value: Any, variables: Mapping[str, Any]) -> Any:
    if isinstance(value, str):
        return _interpolate_string(value, variables)
    if isinstance(value, list):
        return [_interpolate_value(item, variables) for item in value]
    if isinstance(value, dict):
        return {k: _interpolate_value(v, variables) for k, v in value.items()}
    return value


def _validate_target_url(url: str, *, allow_remote: bool) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError(f"unsupported URL scheme {parsed.scheme!r}; only http/https are permitted")
    if not parsed.hostname:
        raise ValueError(f"URL is missing hostname: {url!r}")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("URLs containing embedded credentials are prohibited")
    if not allow_remote and parsed.hostname.lower() not in LOOPBACK_HOSTS:
        raise ValueError(
            f"remote host {parsed.hostname!r} blocked by default safety policy; "
            "set allow_remote=true explicitly for authorized non-loopback targets"
        )
    return url


def _build_case_url(base_url: str, case: Mapping[str, Any], variables: Mapping[str, Any]) -> str:
    if "url" in case and case["url"]:
        raw_url = _interpolate_string(str(case["url"]), variables)
    else:
        path = _interpolate_string(str(case.get("path", "/")), variables)
        raw_url = f"{base_url.rstrip('/')}/{path.lstrip('/')}" if path else base_url
    query = case.get("query")
    if query:
        if not isinstance(query, Mapping):
            raise ValueError("case 'query' must be an object")
        resolved_query = _interpolate_value(dict(query), variables)
        parsed = urlparse(raw_url)
        qs = urlencode(resolved_query, doseq=True)
        combined = f"{parsed.query}&{qs}" if parsed.query else qs
        raw_url = urlunparse(parsed._replace(query=combined))
    return raw_url


def _evaluate_expectations(
    response: ApiResponse,
    expect: Mapping[str, Any],
) -> tuple[list[str], list[str]]:
    checks_passed: list[str] = []
    failures: list[str] = []

    def _run_check(label: str, fn: Callable[[], Any]) -> None:
        try:
            fn()
            checks_passed.append(label)
        except (AssertionError, ValueError) as exc:
            failures.append(f"{label}: {exc}")

    expected_status = expect.get("status", 200)
    _run_check("status", lambda: assert_status(response, expected_status))

    if "max_ms" in expect and expect["max_ms"] is not None:
        max_ms = float(expect["max_ms"])
        _run_check("max_ms", lambda: assert_response_time(response, max_ms=max_ms))

    headers_spec = expect.get("headers") or {}
    if not isinstance(headers_spec, Mapping):
        raise ValueError("expect.headers must be an object")
    for header_name, rule in headers_spec.items():
        h_name = str(header_name)
        if isinstance(rule, str):
            r_str = rule

            def _check_hdr_str(n: str = h_name, r: str = r_str) -> None:
                assert_header(response, n, contains=r)

            _run_check(f"header:{h_name}", _check_hdr_str)
        elif isinstance(rule, Mapping):
            r_map = rule

            def _check_hdr_map(n: str = h_name, r: Mapping[str, Any] = r_map) -> None:
                assert_header(
                    response,
                    n,
                    equals=r.get("equals"),
                    contains=r.get("contains"),
                    regex=r.get("regex"),
                )

            _run_check(f"header:{h_name}", _check_hdr_map)
        else:
            raise ValueError(f"invalid header expectation for {header_name!r}")

    req_fields = expect.get("json_required_fields")
    if req_fields:
        fields_tuple = tuple(str(f) for f in req_fields)
        _run_check("json_required_fields", lambda: assert_json_fields(response, fields_tuple))

    json_paths = expect.get("json_paths") or []
    for idx, rule in enumerate(json_paths):
        if not isinstance(rule, Mapping) or "path" not in rule:
            raise ValueError(f"expect.json_paths[{idx}] must be an object containing 'path'")
        path = str(rule["path"])
        type_spec = None
        if "type" in rule and rule["type"] is not None:
            type_name = str(rule["type"]).lower()
            if type_name not in _JSON_TYPE_MAP:
                raise ValueError(f"unsupported json_paths type {rule['type']!r}")
            type_spec = _JSON_TYPE_MAP[type_name]
        kwargs: dict[str, Any] = {
            "expected_type": type_spec,
            "min_value": rule.get("min"),
            "max_value": rule.get("max"),
            "regex": rule.get("regex"),
            "min_length": rule.get("min_length"),
            "max_length": rule.get("max_length"),
        }
        if "equals" in rule:
            kwargs["equals"] = rule["equals"]

        def _check_jpath(p: str = path, kw: dict[str, Any] = kwargs) -> None:
            assert_json_path(response, p, **kw)

        _run_check(f"json_path:{path}", _check_jpath)

    body_text = response.text
    for needle in expect.get("body_contains") or []:
        needle_str = str(needle)
        if needle_str in body_text:
            checks_passed.append(f"body_contains:{needle_str}")
        else:
            failures.append(f"body_contains:{needle_str}: substring not found in response body")

    for forbidden in expect.get("body_not_contains") or []:
        forbidden_str = str(forbidden)
        if forbidden_str not in body_text:
            checks_passed.append(f"body_not_contains:{forbidden_str}")
        else:
            failures.append(f"body_not_contains:{forbidden_str}: forbidden substring found in response body")

    snapshot_keys = expect.get("schema_snapshot_keys")
    if snapshot_keys is not None:
        expected_keys = sorted(str(k) for k in snapshot_keys)
        def _check_snapshot() -> None:
            payload = response.json()
            if not isinstance(payload, dict):
                raise AssertionError("schema_snapshot_keys requires a JSON object response")
            actual_keys = sorted(payload.keys())
            missing = sorted(set(expected_keys) - set(actual_keys))
            extra = sorted(set(actual_keys) - set(expected_keys))
            if missing or extra:
                raise AssertionError(f"schema drift detected (missing={missing}, extra={extra})")
        _run_check("schema_snapshot_keys", _check_snapshot)

    return checks_passed, failures


def load_suite_file(path: Path) -> dict[str, Any]:
    """Load and structurally validate a declarative JSON QA suite definition."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("suite file must contain a JSON object")
    if not isinstance(data.get("name"), str) or not data["name"].strip():
        raise ValueError("suite 'name' must be a non-empty string")
    cases = data.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("suite 'cases' must be a non-empty list")
    return data


def _extract_case_variables(
    response: ApiResponse,
    extract_spec: Mapping[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    """Extract chained variables from JSON paths, headers, or regex captures."""
    extracted: dict[str, Any] = {}
    errors: list[str] = []
    for var_name, raw_expr in extract_spec.items():
        expr = str(raw_expr).strip()
        try:
            if expr.startswith("json:"):
                json_path = expr[5:].strip()
                extracted[var_name] = resolve_json_path(response.json(), json_path)
            elif expr.startswith("header:"):
                hdr_name = expr[7:].strip()
                val = response.header(hdr_name)
                if val is None:
                    raise KeyError(f"missing header {hdr_name!r}")
                extracted[var_name] = val
            elif expr.startswith("regex:"):
                pattern = expr[6:]
                match = re.search(pattern, response.text)
                if match is None:
                    raise ValueError(f"regex {pattern!r} did not match response body")
                extracted[var_name] = match.group(1) if match.groups() else match.group(0)
            else:
                extracted[var_name] = resolve_json_path(response.json(), expr)
        except Exception as exc:
            errors.append(f"extract:{var_name}: {exc}")
    return extracted, errors


def run_suite(
    suite: Mapping[str, Any],
    *,
    output_dir: Path | None = None,
    workers: int | None = None,
    requester: Callable[..., ApiResponse] | None = None,
) -> SuiteExecutionResult:
    """Execute a declarative QA suite (with chained extraction & optional concurrency) and emit evidence."""
    suite_name = str(suite.get("name", "")).strip()
    if not suite_name:
        raise ValueError("suite 'name' must be a non-empty string")
    cases = suite.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("suite 'cases' must be a non-empty list")

    variables = dict(suite.get("variables") or {})
    base_url = _interpolate_string(str(suite.get("base_url", "")), variables) if suite.get("base_url") else ""
    variables.setdefault("base_url", base_url)
    allow_remote = bool(suite.get("allow_remote", False))
    default_timeout = float(suite.get("default_timeout_s", 10.0))
    default_headers = dict(suite.get("default_headers") or {})
    follow_redirects = bool(suite.get("follow_redirects", False))
    max_retries = int(suite.get("max_retries", 0))
    if max_retries < 0 or max_retries > 3:
        raise ValueError("max_retries must be between 0 and 3")

    effective_workers = int(workers if workers is not None else suite.get("concurrency", 1))
    if effective_workers < 1:
        raise ValueError("workers/concurrency must be at least 1")

    has_chaining = any(isinstance(c, Mapping) and bool(c.get("extract")) for c in cases)
    if has_chaining:
        effective_workers = 1  # Chained suites must execute sequentially so extracted variables propagate

    seen_ids: set[str] = set()
    validated_cases: list[tuple[int, str, Mapping[str, Any]]] = []
    for idx, raw_case in enumerate(cases, start=1):
        if not isinstance(raw_case, Mapping):
            raise ValueError(f"suite case[{idx}] must be an object")
        case_id = str(raw_case.get("id", f"case-{idx:02d}")).strip()
        if not case_id or case_id in seen_ids:
            raise ValueError(f"duplicate or empty test case id: {case_id!r}")
        seen_ids.add(case_id)
        method = str(raw_case.get("method", "GET")).upper()
        if method not in SAFE_HTTP_METHODS:
            raise ValueError(
                f"case {case_id!r} uses unsupported method {method!r}; "
                f"declarative runner enforces read-only methods: {sorted(SAFE_HTTP_METHODS)}"
            )
        case_retries = int(raw_case.get("max_retries", max_retries))
        if case_retries < 0 or case_retries > 3:
            raise ValueError(f"case {case_id!r} max_retries must be between 0 and 3")
        validated_cases.append((idx, case_id, raw_case))

    pool_ctx = create_pooled_requester(max_connections=max(4, effective_workers * 2)) if requester is None else nullcontext(requester)

    with pool_ctx as active_requester:
        def _execute_one(item: tuple[int, str, Mapping[str, Any]], vars_snapshot: dict[str, Any]) -> tuple[int, EvidenceRecord, dict[str, Any]]:
            _, case_id, raw_case = item
            method = str(raw_case.get("method", "GET")).upper()
            url = _validate_target_url(_build_case_url(base_url, raw_case, vars_snapshot), allow_remote=allow_remote)
            case_headers = _interpolate_value(dict(default_headers), vars_snapshot)
            case_headers.update(_interpolate_value(dict(raw_case.get("headers") or {}), vars_snapshot))
            timeout = float(raw_case.get("timeout_s", default_timeout))
            case_retries = int(raw_case.get("max_retries", max_retries))
            expect = _interpolate_value(dict(raw_case.get("expect") or {}), vars_snapshot)

            attempts = 0
            response: ApiResponse | None = None
            for attempt in range(1, case_retries + 2):
                attempts = attempt
                response = active_requester(
                    url,
                    method=method,
                    headers=case_headers,
                    timeout=timeout,
                    follow_redirects=follow_redirects,
                    use_environment_proxies=False,
                )
                if response.status_code != 0:
                    break

            if response is None:  # pragma: no cover
                raise RuntimeError(f"no response received for case {case_id!r}")

            extracted_vars: dict[str, Any] = {}
            if response.status_code == 0 and response.error:
                status = "BLOCKED"
                checks_passed: list[str] = []
                failures = [f"transport: {response.error}"]
            else:
                checks_passed, failures = _evaluate_expectations(response, expect)
                extract_spec = raw_case.get("extract")
                if isinstance(extract_spec, Mapping) and extract_spec:
                    extracted_vars, extract_errors = _extract_case_variables(response, extract_spec)
                    if extract_errors:
                        failures.extend(extract_errors)
                    else:
                        checks_passed.append(f"extract({','.join(sorted(extracted_vars))})")
                status = "PASS" if not failures else "FAIL"

            record = EvidenceRecord(
                test_id=case_id,
                status=status,
                observed_at=utc_now(),
                target=redact_url(url),
                details={
                    "schema": "saqa.suite_case.v1",
                    "suite": suite_name,
                    "case_name": str(raw_case.get("name", case_id)),
                    "tags": list(raw_case.get("tags") or []),
                    "http_method": method,
                    "status_code": response.status_code,
                    "elapsed_ms": round(response.elapsed_ms, 3),
                    "response_sha256": response.sha256,
                    "attempts": attempts,
                    "checks_passed": checks_passed,
                    "extracted_keys": sorted(extracted_vars),
                    "failure_reasons": failures,
                    "destructive_actions": False,
                },
            )
            return item[0], record, extracted_vars

        records: list[EvidenceRecord] = []
        if effective_workers == 1:
            for item in validated_cases:
                _, rec, new_vars = _execute_one(item, variables)
                variables.update(new_vars)
                records.append(rec)
        else:
            # Validate all URLs upfront before thread dispatch so policy errors surface deterministically
            for _, _, raw_case in validated_cases:
                _validate_target_url(_build_case_url(base_url, raw_case, variables), allow_remote=allow_remote)
            with ThreadPoolExecutor(max_workers=min(effective_workers, len(validated_cases))) as pool:
                results = list(pool.map(lambda it: _execute_one(it, dict(variables)), validated_cases))
            results.sort(key=lambda r: r[0])
            records = [rec for _, rec, _ in results]

    manifest_path: Path | None = None
    manifest_sha: str | None = None
    summary_path: Path | None = None

    if output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = output_dir / "evidence-manifest.json"
        manifest_sha = write_manifest(records, manifest_path)

    analytics = analyze_records(records, manifest_sha256=manifest_sha)

    if output_dir is not None:
        summary_path = output_dir / "suite-summary.json"
        summary_path.write_text(
            json.dumps(
                {
                    "suite_name": suite_name,
                    "manifest_path": str(manifest_path),
                    "manifest_sha256": manifest_sha,
                    "analytics": analytics,
                },
                indent=2,
            ),
            encoding="utf-8",
        )

    return SuiteExecutionResult(
        suite_name=suite_name,
        records=tuple(records),
        analytics=analytics,
        manifest_path=manifest_path,
        manifest_sha256=manifest_sha,
        summary_path=summary_path,
    )


def create_starter_suite(
    *,
    name: str = "saqa-api-smoke",
    base_url: str = "http://127.0.0.1:3000",
) -> dict[str, Any]:
    """Generate a ready-to-edit declarative QA suite template for a local target."""
    return {
        "schema": "saqa.suite.v1",
        "name": name,
        "base_url": base_url,
        "allow_remote": False,
        "default_timeout_s": 10.0,
        "follow_redirects": False,
        "max_retries": 1,
        "default_headers": {
            "Accept": "application/json",
        },
        "variables": {
            "search_term": "apple",
        },
        "cases": [
            {
                "id": "home-page-reachable",
                "name": "Homepage responds within SLA without server errors",
                "path": "/",
                "method": "GET",
                "tags": ["smoke", "web"],
                "expect": {
                    "status": 200,
                    "max_ms": 1500,
                    "body_not_contains": ["Traceback", "ReferenceError", "SQLITE_ERROR"],
                },
            },
            {
                "id": "product-search-contract",
                "name": "Product search endpoint satisfies JSON contract and latency SLA",
                "path": "/rest/products/search",
                "query": {"q": "{{search_term}}"},
                "method": "GET",
                "tags": ["smoke", "api", "contract"],
                "expect": {
                    "status": 200,
                    "max_ms": 1500,
                    "headers": {
                        "content-type": {"contains": "application/json"},
                    },
                    "json_required_fields": ["status", "data"],
                    "json_paths": [
                        {"path": "status", "equals": "success", "type": "string"},
                        {"path": "data", "type": "array", "min_length": 1},
                    ],
                },
            },
        ],
    }
