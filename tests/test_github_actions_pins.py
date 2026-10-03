import pytest
from scripts import validate_github_actions_pins as validator
from scripts.validate_github_actions_pins import PINNED_USES, USES_START

def test_action_pin_parser_accepts_full_sha_and_yaml_comment():
    line = '  - uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262 # v4'
    assert USES_START.match(line)
    assert PINNED_USES.match(line)

@pytest.mark.parametrize("line", [
    '  - "uses": "actions/checkout@11d5960a326750d5838078e36cf38b85af677262" # quoted',
    '  - uses: "actions/checkout@11d5960a326750d5838078e36cf38b85af677262"',
])
def test_action_pin_parser_accepts_quoted_yaml_forms(line):
    assert USES_START.match(line)
    assert PINNED_USES.match(line)

def test_action_pin_parser_rejects_mutable_and_malformed_refs():
    invalid = [
        "uses: actions/checkout@main",
        "uses: actions/checkout@v6",
        "uses: actions/checkout@11d5960a326750d5838078e36cf38b85af67726",
        "uses: actions/checkout@not-a-sha",
    ]
    assert all(USES_START.match(line) and not PINNED_USES.match(line) for line in invalid)

def test_validator_fails_closed_on_empty_directory(monkeypatch, tmp_path):
    monkeypatch.setattr(validator, "WORKFLOWS", tmp_path)
    with pytest.raises(SystemExit, match="No GitHub Actions"):
        validator.main()

def test_validator_rejects_mutable_reference(monkeypatch, tmp_path):
    (tmp_path / "ci.yml").write_text("steps:\n  - uses: actions/checkout@main\n", encoding="utf-8")
    monkeypatch.setattr(validator, "WORKFLOWS", tmp_path)
    with pytest.raises(SystemExit, match="Mutable"):
        validator.main()

def test_validator_accepts_local_and_digest_container_references(monkeypatch, tmp_path):
    (tmp_path / "ci.yml").write_text(
        "steps:\n"
        "  - uses: ./actions/local-check\n"
        "  - uses: docker://alpine@sha256:" + "a" * 64 + "\n"
        "  - uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(validator, "WORKFLOWS", tmp_path)
    assert validator.main() == 0

def test_validator_counts_non_external_uses_references(monkeypatch, tmp_path):
    (tmp_path / "ci.yml").write_text(
        "steps:\n"
        "  - uses: ./actions/local-check\n"
        "  - uses: docker://alpine@sha256:" + "a" * 64 + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(validator, "WORKFLOWS", tmp_path)
    assert validator.main() == 0

def test_validator_rejects_non_digest_docker_reference(monkeypatch, tmp_path):
    (tmp_path / "ci.yml").write_text(
        "steps:\n"
        "  - uses: docker://alpine:latest\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(validator, "WORKFLOWS", tmp_path)
    with pytest.raises(SystemExit, match="Docker action reference"):
        validator.main()


def test_validator_accepts_digest_container_reference_with_yaml_comment(monkeypatch, tmp_path):
    (tmp_path / "ci.yml").write_text(
        "steps:\n"
        "  - uses: docker://alpine@sha256:" + "a" * 64 + " # pinned\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(validator, "WORKFLOWS", tmp_path)
    assert validator.main() == 0
