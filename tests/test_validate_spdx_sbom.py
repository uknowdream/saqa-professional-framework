import json
import pytest
from scripts.validate_spdx_sbom import SCHEMA, validate_file, validate_spdx


def valid_spdx():
    return {
        "spdxVersion": "SPDX-2.3", "SPDXID": "SPDXRef-DOCUMENT",
        "name": "juice-shop", "documentNamespace": "https://example.invalid/spdx/juice-shop",
        "creationInfo": {"creators": ["Tool: Syft"]},
        "packages": [{"SPDXID": "SPDXRef-Package-1", "name": "example-package"}],
    }


def test_valid_spdx_has_digest_and_inventory():
    result = validate_spdx(valid_spdx(), source="sbom.json", digest="a" * 64)
    assert result["schema"] == SCHEMA
    assert result["status"] == "PASS"
    assert result["package_count"] == 1
    assert result["sha256"] == "a" * 64


@pytest.mark.parametrize("payload", [None, [], "sbom", {}])
def test_invalid_root_or_missing_fields_rejected(payload):
    with pytest.raises(ValueError):
        validate_spdx(payload, source="sbom.json", digest="a" * 64)


def test_duplicate_package_ids_rejected():
    data = valid_spdx()
    data["packages"].append({"SPDXID": "SPDXRef-Package-1", "name": "duplicate"})
    with pytest.raises(ValueError, match="duplicate package SPDXID"):
        validate_spdx(data, source="sbom.json", digest="a" * 64)


def test_invalid_package_rejected():
    data = valid_spdx()
    data["packages"] = [{"SPDXID": "SPDXRef-Package-1"}]
    with pytest.raises(ValueError, match=r"packages\[0\].name"):
        validate_spdx(data, source="sbom.json", digest="a" * 64)


def test_invalid_json_fails_and_removes_stale_output(tmp_path):
    source, output = tmp_path / "sbom.json", tmp_path / "validated.json"
    source.write_text("{", encoding="utf-8")
    output.write_text('{"status":"PASS"}', encoding="utf-8")
    with pytest.raises(ValueError, match="cannot read SBOM JSON"):
        validate_file(source, output)
