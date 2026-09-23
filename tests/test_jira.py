from __future__ import annotations

import json

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


def test_jira_create_bug_uses_bug_issue_type() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["payload"] = json.loads(request.read())
        return httpx.Response(201, json={"id": "10002", "key": "QA-10"})

    config = JiraConfig("https://jira.example", "qa@example.com", "secret-token", "QA")
    client = JiraClient(config, timeout=1.0)
    client._client = httpx.Client(transport=httpx.MockTransport(handler), base_url=config.base_url)
    try:
        issue = client.create_bug("[SAQA-AUTO] failure", "Verified CI failure", ["saqa-auto-defect"])
    finally:
        client.close()

    assert issue.key == "QA-10"
    assert seen["payload"]["fields"]["issuetype"] == {"name": "Bug"}
    assert seen["payload"]["fields"]["labels"] == ["saqa-auto-defect"]


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


def test_jira_update_labels_sends_add_and_remove_operations() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["path"] = request.url.path
        seen["payload"] = json.loads(request.read())
        return httpx.Response(204)

    config = JiraConfig("https://jira.example", "qa@example.com", "secret-token", "QA")
    client = JiraClient(config, timeout=1.0)
    client._client = httpx.Client(transport=httpx.MockTransport(handler), base_url=config.base_url)
    try:
        client.update_labels("QA-4", add=("saqa-automation", "saqa-ci-pass"), remove=("saqa-ci-fail",))
    finally:
        client.close()

    assert seen["method"] == "PUT"
    assert seen["path"] == "/rest/api/3/issue/QA-4"
    assert seen["payload"] == {
        "update": {
            "labels": [
                {"add": "saqa-automation"},
                {"add": "saqa-ci-pass"},
                {"remove": "saqa-ci-fail"},
            ]
        }
    }


def test_jira_comment_is_idempotent_when_marker_already_exists() -> None:
    calls: list[str] = []
    marker = "[SAQA-AUTO-SYNC:123:QA-4]"

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.method == "GET":
            return httpx.Response(200, json={"comments": [{"body": {"content": [{"text": marker}]}}]})
        raise AssertionError("duplicate marker must not create a second comment")

    config = JiraConfig("https://jira.example", "qa@example.com", "secret-token", "QA")
    client = JiraClient(config, timeout=1.0)
    client._client = httpx.Client(transport=httpx.MockTransport(handler), base_url=config.base_url)
    try:
        assert client.add_comment_once("QA-4", "result", marker) is False
    finally:
        client.close()

    assert calls == ["/rest/api/3/issue/QA-4/comment"]


def test_jira_transition_uses_only_an_available_exact_transition() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path.endswith("/transitions") and request.method == "GET":
            return httpx.Response(200, json={"transitions": [{"id": "31", "name": "Complete", "to": {"name": "Done"}}]})
        if request.url.path.endswith("/QA-9") and request.method == "GET":
            return httpx.Response(200, json={"fields": {"status": {"name": "In Progress"}, "labels": []}})
        if request.url.path.endswith("/transitions") and request.method == "POST":
            return httpx.Response(204)
        raise AssertionError(f"unexpected request: {request.method} {request.url.path}")

    config = JiraConfig("https://jira.example", "qa@example.com", "secret-token", "QA")
    client = JiraClient(config, timeout=1.0)
    client._client = httpx.Client(transport=httpx.MockTransport(handler), base_url=config.base_url)
    try:
        assert client.transition_to_any("QA-9", ("Done",)) == "Done"
    finally:
        client.close()

    assert calls == [
        "/rest/api/3/issue/QA-9/transitions",
        "/rest/api/3/issue/QA-9",
        "/rest/api/3/issue/QA-9/transitions",
    ]


def test_jira_find_project_issues_reads_multiple_pages() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        start = int(request.url.params.get("startAt", "0"))
        calls.append(start)
        if start == 0:
            issues = [{"key": f"QA-{i}", "id": str(i), "fields": {"summary": f"Summary {i}"}} for i in range(100)]
            return httpx.Response(200, json={"issues": issues})
        return httpx.Response(200, json={"issues": [{"key": "QA-101", "id": "101", "fields": {"summary": "SAQA | Web E2E Automation"}}]})

    config = JiraConfig("https://jira.example", "qa@example.com", "secret-token", "QA")
    client = JiraClient(config, timeout=1.0)
    client._client = httpx.Client(transport=httpx.MockTransport(handler), base_url=config.base_url)
    try:
        result = client.find_project_issues(max_results=200)
    finally:
        client.close()

    assert "SAQA | Web E2E Automation" in result
    assert calls == [0, 100]


def test_jira_find_project_issues_detects_managed_duplicate_summary() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        start = int(request.url.params.get("startAt", "0"))
        if start == 0:
            issues = [{"key": f"QA-{i}", "id": str(i), "fields": {"summary": f"Summary {i}"}} for i in range(100)]
            return httpx.Response(200, json={"issues": issues})
        return httpx.Response(200, json={"issues": [{"key": "QA-101", "id": "101", "fields": {"summary": "[SAQA-AUTO] duplicate"}}]})

    config = JiraConfig("https://jira.example", "qa@example.com", "secret-token", "QA")
    client = JiraClient(config, timeout=1.0)
    client._client = httpx.Client(transport=httpx.MockTransport(handler), base_url=config.base_url)
    try:
        with pytest.raises(RuntimeError, match="duplicate managed summary"):
            client.find_project_issues(max_results=200)
    finally:
        client.close()


def test_jira_comment_marker_is_found_beyond_first_page() -> None:
    marker = "[SAQA-AUTO-SYNC:123:QA-4]"
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        start = int(request.url.params.get("startAt", "0"))
        calls.append(start)
        if start == 0:
            return httpx.Response(200, json={"comments": [{"body": {"content": [{"text": "older"}]}}], "total": 101})
        if start == 1:
            return httpx.Response(200, json={"comments": [{"body": {"content": [{"text": marker}]}}], "total": 2})
        return httpx.Response(200, json={"comments": [], "total": 101})

    config = JiraConfig("https://jira.example", "qa@example.com", "secret-token", "QA")
    client = JiraClient(config, timeout=1.0)
    client._client = httpx.Client(transport=httpx.MockTransport(handler), base_url=config.base_url)
    try:
        assert client.add_comment_once("QA-4", "result", marker) is False
    finally:
        client.close()

    assert calls == [0, 1]


def test_jira_client_uses_basic_auth_header():
    import base64
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["authorization"] = request.headers.get("Authorization", "")
        return httpx.Response(200, json={"key": "QA", "name": "Quality", "projectTypeKey": "software"})

    config = JiraConfig("https://jira.example", "qa@example.com", "secret-token", "QA")
    client = JiraClient(config, timeout=1.0)
    client._client = httpx.Client(
        transport=httpx.MockTransport(handler),
        base_url=config.base_url,
        auth=(config.email, config.api_token),
    )
    try:
        assert client.verify_access().key == "QA"
    finally:
        client.close()
    expected = "Basic " + base64.b64encode(b"qa@example.com:secret-token").decode()
    assert seen["authorization"] == expected
