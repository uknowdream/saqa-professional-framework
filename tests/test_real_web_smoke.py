from scripts.real_web_smoke import TargetPolicyError, validate_target


def test_real_web_requires_explicit_allowlist(monkeypatch):
    monkeypatch.setenv("SAQA_REAL_WEB_ALLOWLIST", "approved.example")
    validate_target("https://approved.example/health")


def test_real_web_rejects_unlisted_host(monkeypatch):
    monkeypatch.setenv("SAQA_REAL_WEB_ALLOWLIST", "approved.example")
    try:
        validate_target("https://other.example/")
    except TargetPolicyError:
        return
    raise AssertionError("unlisted host must be rejected")


def test_real_web_rejects_http_by_default(monkeypatch):
    monkeypatch.setenv("SAQA_REAL_WEB_ALLOWLIST", "approved.example")
    monkeypatch.delenv("SAQA_ALLOW_HTTP_REAL_WEB", raising=False)
    try:
        validate_target("http://approved.example/")
    except TargetPolicyError:
        return
    raise AssertionError("HTTP must be rejected unless explicitly enabled")


def test_real_web_rejects_embedded_credentials(monkeypatch):
    monkeypatch.setenv("SAQA_REAL_WEB_ALLOWLIST", "approved.example")
    try:
        validate_target("https://user:pass@approved.example/")
    except TargetPolicyError:
        return
    raise AssertionError("embedded credentials must be rejected")
