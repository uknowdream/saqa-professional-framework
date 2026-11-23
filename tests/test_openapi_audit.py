"""Unit tests for automated OpenAPI contract generator & auditor (saqa.openapi_audit)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from saqa.api import ApiResponse
from saqa.cli import main as cli_main
from saqa.evidence import verify_manifest
from saqa.openapi_audit import audit_openapi_spec, generate_suite_from_openapi, load_openapi_spec

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_generate_suite_from_checked_in_juice_shop_openapi():
    spec_path = REPO_ROOT / "contracts" / "juice-shop.openapi.json"
    spec = load_openapi_spec(spec_path)
    suite = generate_suite_from_openapi(spec, base_url="http://127.0.0.1:3000")
    assert suite["schema"] == "saqa.suite.v1"
    assert len(suite["cases"]) >= 1
    assert all(case["method"] == "GET" for case in suite["cases"])


def test_audit_openapi_spec_executes_generated_cases_and_cli_export(tmp_path):
    spec = {
        "openapi": "3.0.3",
        "info": {"title": "Catalog API", "version": "1.0.0"},
        "paths": {
            "/items/{id}": {
                "get": {
                    "operationId": "getItemById",
                    "summary": "Fetch item by ID",
                    "parameters": [
                        {"name": "id", "in": "path", "required": True, "schema": {"type": "integer", "example": 42}},
                        {"name": "format", "in": "query", "schema": {"type": "string", "enum": ["compact"]}},
                    ],
                    "responses": {
                        "200": {
                            "description": "OK",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "required": ["id", "name"],
                                    }
                                }
                            },
                        }
                    },
                }
            }
        },
    }
    spec_file = tmp_path / "catalog.openapi.json"
    spec_file.write_text(json.dumps(spec), encoding="utf-8")

    seen_urls: list[str] = []

    def fake_req(url, **kwargs):
        seen_urls.append(url)
        return ApiResponse(200, {"Content-Type": "application/json"}, b'{"id": 42, "name": "Widget"}', 14.0)

    out_dir = tmp_path / "out"
    result = audit_openapi_spec(spec_file, base_url="http://127.0.0.1:8080", output_dir=out_dir, requester=fake_req)
    assert result.passed is True
    assert seen_urls == ["http://127.0.0.1:8080/items/42?format=compact"]
    assert result.manifest_path is not None and verify_manifest(result.manifest_path)

    exported = tmp_path / "exported-suite.json"
    assert cli_main(["audit-openapi", str(spec_file), "--export-suite", str(exported)]) == 0
    assert exported.is_file()


def test_openapi_spec_validation_rejects_malformed_specs(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text('{"paths": {}}', encoding="utf-8")
    with pytest.raises(ValueError, match="openapi"):
        load_openapi_spec(bad)

    empty_get = {"openapi": "3.0.0", "paths": {"/only-post": {"post": {}}}}
    with pytest.raises(ValueError, match="no read-only GET"):
        generate_suite_from_openapi(empty_get)
