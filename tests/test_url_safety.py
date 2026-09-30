from saqa.url_safety import redact_url


def test_redact_url_removes_sensitive_components_and_preserves_ipv6():
    assert redact_url("http://user:secret@127.0.0.1:3000/private;token?q=hidden#fragment") == "http://127.0.0.1:3000"
    assert redact_url("http://[::1]:3000/private;token") == "http://[::1]:3000"
    assert redact_url("https://example.com/path") == "https://example.com"
