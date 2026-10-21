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
    assert validate_report(payload) == {
        "dependency_count": 1, "audited_dependency_count": 1, "vulnerability_count": 1,
        "skipped_dependency_count": 0, "skipped_dependencies": [], "fix_count": 0,
    }


def test_empty_valid_report_has_zero_findings():
    expected = {
        "dependency_count": 0, "audited_dependency_count": 0, "vulnerability_count": 0,
        "skipped_dependency_count": 0, "skipped_dependencies": [], "fix_count": 0,
    }
    assert validate_report([]) == expected
    assert validate_report({"dependencies": [], "fixes": []}) == expected


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


def test_known_local_project_skip_is_explicit_and_does_not_count_as_audited():
    skipped = {
        "name": "saqa-professional-framework",
        "skip_reason": (
            "Dependency not found on PyPI and could not be audited: "
            "saqa-professional-framework (2.1.0)"
        ),
    }
    result = validate_report({"dependencies": [DEPENDENCY, skipped], "fixes": []})
    assert result["dependency_count"] == 2
    assert result["audited_dependency_count"] == 1
    assert result["vulnerability_count"] == 1
    assert result["skipped_dependency_count"] == 1
    assert result["skipped_dependencies"] == [skipped]
    assert result["fix_count"] == 0


@pytest.mark.parametrize("dependency", [
    {"name": "external-package", "skip_reason": "Dependency not found on PyPI and could not be audited: external-package (1.0)"},
    {"name": "saqa-professional-framework", "skip_reason": "unsupported skip"},
    {"name": "saqa-professional-framework", "skip_reason": "Dependency not found on PyPI and could not be audited: saqa-professional-framework (2.1.0"},
])
def test_unknown_or_malformed_skip_records_fail_closed(dependency):
    with pytest.raises(ValueError, match="skip reason"):
        validate_report({"dependencies": [dependency]})


def test_duplicate_local_skip_is_rejected():
    skip = {
        "name": "saqa-professional-framework",
        "skip_reason": (
            "Dependency not found on PyPI and could not be audited: "
            "saqa-professional-framework (2.1.0)"
        ),
    }
    with pytest.raises(ValueError, match="duplicate skipped local project"):
        validate_report({"dependencies": [skip, skip]})


def test_dict_report_rejects_malformed_fixes_collection():
    with pytest.raises(ValueError, match="fixes must be an array"):
        validate_report({"dependencies": [], "fixes": {}})
