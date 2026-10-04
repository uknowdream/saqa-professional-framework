import pytest
from scripts import validate_github_actions_pins as validator
from scripts.validate_github_actions_pins import PINNED_REFERENCE, USES_START


SHA = "11d5960a326750d5838078e36cf38b85af677262"
DIGEST = "a" * 64


def test_action_pin_parser_accepts_full_sha_and_yaml_comment():
    line = f"  - uses: actions/checkout@{SHA} # v4"
    assert USES_START.match(line)
    assert PINNED_REFERENCE.fullmatch(validator._extract_reference(line))


@pytest.mark.parametrize(
    "line",
    [
        f'  - "uses": "actions/checkout@{SHA}" # quoted',
        f'  - uses: "actions/checkout@{SHA}"',
        f"  - uses: 'actions/checkout@{SHA}' # quoted",
    ],
)
def test_action_pin_parser_accepts_quoted_yaml_forms(line):
    assert USES_START.match(line)
    assert PINNED_REFERENCE.fullmatch(validator._extract_reference(line))


def test_comment_stripping_preserves_hash_inside_quotes():
    line = f'  - uses: "actions/checkout@{SHA}#literal"'
    assert validator._extract_reference(line) == f"actions/checkout@{SHA}#literal"
    assert not PINNED_REFERENCE.fullmatch(validator._extract_reference(line))


@pytest.mark.parametrize(
    "line",
    [
        "uses: actions/checkout@main",
        "uses: actions/checkout@v6",
        "uses: actions/checkout@11d5960a326750d5838078e36cf38b85af67726",
        "uses: actions/checkout@not-a-sha",
        f"uses: actions/checkout@{SHA} extra",
    ],
)
def test_action_pin_parser_rejects_mutable_and_malformed_refs(line):
    assert USES_START.match(line)
    assert not PINNED_REFERENCE.fullmatch(validator._extract_reference(line))


def test_validator_fails_closed_on_empty_directory(monkeypatch, tmp_path):
    monkeypatch.setattr(validator, "WORKFLOWS", tmp_path)
    with pytest.raises(SystemExit, match="No GitHub Actions"):
        validator.main()


def test_validator_rejects_mutable_reference(monkeypatch, tmp_path):
    (tmp_path / "ci.yml").write_text(
        "steps:\n  - uses: actions/checkout@main\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(validator, "WORKFLOWS", tmp_path)
    with pytest.raises(SystemExit, match="Mutable"):
        validator.main()


def test_validator_accepts_local_and_digest_container_references(monkeypatch, tmp_path):
    (tmp_path / "ci.yml").write_text(
        "steps:\n"
        "  - uses: ./actions/local-check\n"
        "  - uses: docker://alpine@sha256:" + DIGEST + "\n"
        f"  - uses: actions/checkout@{SHA}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(validator, "WORKFLOWS", tmp_path)
    assert validator.main() == 0


def test_validator_counts_non_external_uses_references(monkeypatch, tmp_path):
    (tmp_path / "ci.yml").write_text(
        "steps:\n"
        "  - uses: ./actions/local-check\n"
        "  - uses: docker://alpine@sha256:" + DIGEST + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(validator, "WORKFLOWS", tmp_path)
    assert validator.main() == 0


def test_validator_accepts_digest_container_reference_with_yaml_comment(monkeypatch, tmp_path):
    (tmp_path / "ci.yml").write_text(
        "steps:\n"
        "  - uses: docker://alpine@sha256:" + DIGEST + " # pinned\n",
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


def test_validator_rejects_quoted_digest_with_trailing_comment_only_after_unquoting(monkeypatch, tmp_path):
    (tmp_path / "ci.yml").write_text(
        'steps:\n'
        '  - uses: "docker://alpine@sha256:' + DIGEST + '" # pinned\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(validator, "WORKFLOWS", tmp_path)
    assert validator.main() == 0
