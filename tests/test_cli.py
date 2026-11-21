"""Unit tests for saqa.cli."""
from __future__ import annotations

import json

from saqa import __version__
from saqa.cli import main
from saqa.evidence import EvidenceRecord, utc_now, write_manifest


def test_cli_version(capsys):
    assert main(["version"]) == 0
    assert __version__ in capsys.readouterr().out


def test_cli_targets_text_and_json(capsys):
    assert main(["targets"]) == 0
    text_out = capsys.readouterr().out
    assert "owasp-juice-shop" in text_out
    assert "owasp-webgoat" in text_out

    assert main(["targets", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    names = {item["name"] for item in payload}
    assert {"owasp-juice-shop", "owasp-webgoat"}.issubset(names)


def test_cli_verify_manifest_valid_and_invalid(tmp_path, capsys):
    manifest = tmp_path / "manifest.json"
    record = EvidenceRecord(
        test_id="cli-test-1",
        status="PASS",
        observed_at=utc_now(),
        target="http://127.0.0.1:3000",
        details={"ok": True},
    )
    write_manifest([record], manifest)

    assert main(["verify-manifest", str(manifest)]) == 0
    assert "MANIFEST_VALID" in capsys.readouterr().out

    manifest.write_text('{"records": [], "sha256": "invalid"}', encoding="utf-8")
    assert main(["verify-manifest", str(manifest)]) == 1
    assert "MANIFEST_INVALID" in capsys.readouterr().err
