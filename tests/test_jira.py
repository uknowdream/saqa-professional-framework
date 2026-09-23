from __future__ import annotations

import httpx
import pytest

from saqa.jira import JiraClient, JiraConfig

# ... existing tests above remain unchanged ...


def test_jira_find_project_issues_detects_managed_duplicate_summary() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        start = int(request.url.params.get("startAt", "0"))
        if start == 0:
            issues = [{"key": f"QA-{i}", "id": str(i), "fields": {"summary": f"Summary {i}"}} for i in range(100)]
            issues.append({"key": "QA-100", "id": "100", "fields": {"summary": "[SAQA-AUTO] duplicate"}})
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
