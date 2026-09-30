from scripts.validate_github_actions_pins import PINNED_USES, USES_START


def test_action_pin_parser_accepts_full_sha_and_yaml_comment():
    line = "  - uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262 # v4"
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
