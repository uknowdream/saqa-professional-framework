import json

import pytest

from scripts.validate_pip_audit_report import main, validate_report


DEPENDENCY = {
    "name": "demo-package",
    "version": "1.2.3",
    "vulns": [
        {"id": "PYSEC-2026-123", "fix_versions": ["1.2.4"], "aliases": ["GHSA-demo-1234"]}
    ],
}


@pytest.mark.parametrize("payload", [
    [DEPENDENCY],
    {"dependencies": [DEPENDENCY]},
])
def test_supported_report_root_schemas_are_validated(payload):
    assert validate_report(payload) == {"dependency_count": 1, "vulnerability_count": 1}


def test_empty_valid_report_has_zero_findings():
    assert validate_report([]) == {"dependency_count": 0, "vulnerability_count": 0}
    assert validate_report({"dependencies": []}) == {"dependency_count": 0, "vulnerability_count": 0}


@pytest.mark.parametrize("payload", [None, {}, "report", {"dependencies": {}}, {"dependencies": None}])
def test_invalid_report_root_or_dependency_collection_is_rejected(payload):
    with pytest.raises(ValueError, match="dependency array"):
        validate_report(payload)


@pytest.mark.parametrize("dependency", [
    None,
    "bad",
    {},
    {"name": "", "version": "1.0", "vulns": []},
    {"name": "package", "version": None, "vulns": []},
    {"name": "package", "version": "1.0", "vulns": None},
    {"name": "package", "version": "1.0", "vulns": ["bad"]},
])
def test_malformed_dependency_record_is_rejected(dependency):
    with pytest.raises(ValueError, match="dependency"):
        validate_report([dependency])


@pytest.mark.parametrize("vulnerability", [
    None,
    [],
    {},
    {"id": ""},
    {"id": "CVE-2026-1234", "aliases": "CVE-OTHER"},
    {"id": "CVE-2026-1234", "fix_versions": [3]},
])
def test_malformed_vulnerability_record_is_rejected(vulnerability):
    dependency = {"name": "package", "version": "1.0", "vulns": [vulnerability]}
    with pytest.raises(ValueError, match="vulns"):
        validate_report([dependency])


def test_main_reports_malformed_json_as_unverified(tmp_path, capsys):
    path = tmp_path / "pip-audit.json"
    path.write_text("{", encoding="utf-8")
    assert main(["--input", str(path)]) == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "UNVERIFIED"
