"""Automated OpenAPI 3.x / Swagger 2.0 zero-code QA suite generator and contract auditor."""
from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from .api import ApiResponse
from .api import request as http_request
from .runner import SuiteExecutionResult, run_suite

_PATH_PARAM_RE = re.compile(r"\{([^}]+)\}")


def load_openapi_spec(path: Path) -> dict[str, Any]:
    """Load and structurally validate an OpenAPI 3.x or Swagger 2.0 JSON file."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("OpenAPI specification must be a JSON object")
    if "paths" not in data or not isinstance(data["paths"], dict):
        raise ValueError("OpenAPI specification must contain a 'paths' object")
    if not (data.get("openapi") or data.get("swagger")):
        raise ValueError("OpenAPI specification must declare 'openapi' or 'swagger' version")
    return data


def _sample_param_value(param: Mapping[str, Any]) -> str:
    if "example" in param and param["example"] is not None:
        return str(param["example"])
    schema = param.get("schema") if isinstance(param.get("schema"), Mapping) else param
    if isinstance(schema, Mapping):
        if "default" in schema and schema["default"] is not None:
            return str(schema["default"])
        if "example" in schema and schema["example"] is not None:
            return str(schema["example"])
        enum_vals = schema.get("enum")
        if isinstance(enum_vals, list) and enum_vals:
            return str(enum_vals[0])
        stype = str(schema.get("type", "string")).lower()
        if stype in {"integer", "number"}:
            return "1"
        if stype == "boolean":
            return "true"
    return "apple"


def _extract_required_json_fields(operation: Mapping[str, Any]) -> list[str]:
    responses = operation.get("responses")
    if not isinstance(responses, Mapping):
        return []
    ok_resp = responses.get("200") or responses.get("201")
    if not isinstance(ok_resp, Mapping):
        return []
    # OpenAPI 3.x
    content = ok_resp.get("content")
    schema = None
    if isinstance(content, Mapping):
        app_json = content.get("application/json")
        if isinstance(app_json, Mapping):
            schema = app_json.get("schema")
    # Swagger 2.0
    if schema is None:
        schema = ok_resp.get("schema")
    if isinstance(schema, Mapping) and isinstance(schema.get("required"), list):
        return [str(field) for field in schema["required"] if isinstance(field, str)]
    return []


def generate_suite_from_openapi(
    spec: Mapping[str, Any],
    *,
    base_url: str = "http://127.0.0.1:3000",
    allow_remote: bool = False,
    max_ms: float = 2000.0,
) -> dict[str, Any]:
    """Generate a ready-to-run read-only SAQA declarative suite from all GET endpoints in an OpenAPI spec."""
    raw_info = spec.get("info")
    info: Mapping[str, Any] = raw_info if isinstance(raw_info, Mapping) else {}
    raw_title = str(info.get("title") or "openapi-service").strip()
    slug = re.sub(r"[^a-z0-9]+", "-", raw_title.lower()).strip("-") or "openapi-service"
    paths = spec.get("paths")
    if not isinstance(paths, Mapping):
        raise ValueError("OpenAPI spec missing paths object")

    cases: list[dict[str, Any]] = []
    for raw_path, path_item in sorted(paths.items()):
        if not isinstance(path_item, Mapping):
            continue
        op = path_item.get("get")
        if not isinstance(op, Mapping):
            continue

        params_list: list[Mapping[str, Any]] = []
        for source in (path_item.get("parameters"), op.get("parameters")):
            if isinstance(source, list):
                params_list.extend(p for p in source if isinstance(p, Mapping))

        param_by_name = {str(p.get("name")): p for p in params_list if p.get("name")}

        def _replace_param(match: re.Match[str], pmap: dict[str, Mapping[str, Any]] = param_by_name) -> str:
            return _sample_param_value(pmap.get(match.group(1), {}))

        resolved_path = _PATH_PARAM_RE.sub(_replace_param, str(raw_path))
        query_params: dict[str, str] = {}
        for p in params_list:
            if str(p.get("in", "")).lower() == "query" and p.get("name"):
                if p.get("required") or "example" in p or isinstance(p.get("schema"), Mapping):
                    query_params[str(p["name"])] = _sample_param_value(p)

        raw_responses = op.get("responses")
        responses: Mapping[str, Any] = raw_responses if isinstance(raw_responses, Mapping) else {}
        ok_codes = [int(code) for code in responses if str(code).isdigit() and 200 <= int(code) < 300]
        expected_status: int | list[int] = ok_codes[0] if len(ok_codes) == 1 else (ok_codes or 200)

        expect: dict[str, Any] = {
            "status": expected_status,
            "max_ms": max_ms,
        }
        req_fields = _extract_required_json_fields(op)
        if req_fields:
            expect["json_required_fields"] = req_fields
            expect["headers"] = {"content-type": {"contains": "application/json"}}

        op_id = str(op.get("operationId") or f"get-{resolved_path}")
        case_id = re.sub(r"[^a-z0-9_-]+", "-", op_id.lower()).strip("-") or f"endpoint-{len(cases) + 1}"
        case_entry: dict[str, Any] = {
            "id": case_id,
            "name": str(op.get("summary") or f"GET {raw_path}"),
            "path": resolved_path,
            "method": "GET",
            "tags": ["api", "contract", "openapi"],
            "expect": expect,
        }
        if query_params:
            case_entry["query"] = query_params
        cases.append(case_entry)

    if not cases:
        raise ValueError("OpenAPI specification contains no read-only GET endpoints")

    return {
        "schema": "saqa.suite.v1",
        "name": f"{slug}-openapi-contract-audit",
        "base_url": base_url,
        "allow_remote": allow_remote,
        "default_timeout_s": 10.0,
        "follow_redirects": False,
        "max_retries": 1,
        "default_headers": {"Accept": "application/json"},
        "cases": cases,
    }


def audit_openapi_spec(
    spec_path: Path,
    *,
    base_url: str = "http://127.0.0.1:3000",
    allow_remote: bool = False,
    output_dir: Path | None = None,
    requester: Callable[..., ApiResponse] = http_request,
) -> SuiteExecutionResult:
    """Load an OpenAPI JSON spec, auto-generate all GET contract tests, and execute them."""
    spec = load_openapi_spec(spec_path)
    suite = generate_suite_from_openapi(spec, base_url=base_url, allow_remote=allow_remote)
    return run_suite(suite, output_dir=output_dir, requester=requester)
