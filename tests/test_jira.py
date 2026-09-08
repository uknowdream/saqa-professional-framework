from __future__ import annotations

import httpx
import pytest

from saqa.jira import JiraClient, JiraConfig


def test_jira_config_requires_all_runtime_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in ("JIRA_BASE_URL", "JIRA_EMAIL", "JIRA_API_TOKEN", "JIRA_PROJECT_KEY"):
        monkeypatch.delenv(key, raising=False)
    with pytest.raises(ValueError, match="Missing Jira configuration"):
        JiraConfig.from_env()


def test_jira_config_rejects_non_https(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JIRA_BASE_URL", "http://jira.example")
    monkeypatch.setenv("JIRA_EMAIL", "qa@example.com")
    monkeypatch.setenv("JIRA_API_TOKEN", "runtime-only-token")
    monkeypatch.setenv("JIRA_PROJECT_KEY", "QA")
    with pytest.raises(ValueError, match="HTTPS"):
        JiraConfig.from_env()


def test_jira_config_normalizes_base_url_without_exposing_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JIRA_BASE_URL", "https://jira.example/")
    monkeypatch.setenv("JIRA_EMAIL", "qa@example.com")
    monkeypatch.setenv("JIRA_API_TOKEN", "runtime-only-token")
    monkeypatch.setenv("JIRA_PROJECT_KEY", "QA")
    config = JiraConfig.from_env()
    assert config.base_url == "https://jira.example"
    assert config.project_key == "QA"
    assert config.api_token == "runtime-only-token"


def test_jira_create_task_uses_safe_payload_and_returns_issue() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["path"] = request.url.path
        seen["payload"] = request.read().decode()
        return httpx.Response(201, json={"id": "10001", "key": "QA-1"})

    config = JiraConfig("https://jira.example", "qa@example.com", "secret-token", "QA")
    client = JiraClient(config, timeout=1.0)
    client._client = httpx.Client(transport=httpx.MockTransport(handler), base_url=config.base_url)
    try:
        issue = client.create_task("SAQA test", "Controlled QA task", ["saqa-bootstrap"])
    finally:
        client.close()

    assert issue.key == "QA-1"
    assert issue.url.endswith("/browse/QA-1")
    assert seen["method"] == "POST"
    assert seen["path"] == "/rest/api/3/issue"
    assert "secret-token" not in str(seen["payload"])


def test_jira_create_task_rejects_write_authorization_failure() -> None:
    config = JiraConfig("https://jira.example", "qa@example.com", "secret-token", "QA")
    client = JiraClient(config, timeout=1.0)
    client._client = httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(403, json={"error": "forbidden"})),
        base_url=config.base_url,
    )
    try:
        with pytest.raises(RuntimeError, match="write authorization failed"):
            client.create_task("SAQA test", "Controlled QA task", ["saqa-bootstrap"])
    finally:
        client.close()
