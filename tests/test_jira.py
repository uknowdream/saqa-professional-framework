from __future__ import annotations

import pytest

from saqa.jira import JiraConfig


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
