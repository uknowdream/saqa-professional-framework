"""Secure Jira Cloud integration for CI verification and controlled write-back."""
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

import httpx

_RETRYABLE_STATUS_CODES = frozenset({429, 502, 503, 504})


class JiraServiceUnavailableError(RuntimeError):
    """Raised when Jira Cloud is unreachable, hibernated, or returning 5xx/503."""

    def __init__(self, message: str, *, status_code: int | None = None, url: str = "") -> None:
        super().__init__(message)
        self.status_code = status_code
        self.url = url


@dataclass(frozen=True, slots=True)
class JiraConfig:
    base_url: str
    email: str
    api_token: str
    project_key: str

    @classmethod
    def from_env(cls) -> "JiraConfig":
        values = {
            "base_url": os.getenv("JIRA_BASE_URL", "").strip().rstrip("/"),
            "email": os.getenv("JIRA_EMAIL", "").strip(),
            "api_token": os.getenv("JIRA_API_TOKEN", ""),
            "project_key": os.getenv("JIRA_PROJECT_KEY", "").strip(),
        }
        missing = [key for key, value in values.items() if not value]
        if missing:
            raise ValueError("Missing Jira configuration: " + ", ".join(missing))
        if not values["base_url"].startswith("https://"):
            raise ValueError("JIRA_BASE_URL must use HTTPS")
        return cls(**values)


@dataclass(frozen=True, slots=True)
class JiraProjectResult:
    key: str
    name: str
    project_type: str


@dataclass(frozen=True, slots=True)
class JiraIssueResult:
    key: str
    id: str
    url: str


@dataclass(frozen=True, slots=True)
class JiraIssueState:
    key: str
    status: str
    labels: tuple[str, ...]


class JiraClient:
    """Jira Cloud client with read-only verification, retry resilience, and controlled write-back."""

    def __init__(
        self,
        config: JiraConfig,
        timeout: float = 15.0,
        *,
        max_retries: int = 3,
        retry_backoff_s: float | None = None,
    ) -> None:
        if max_retries < 1:
            raise ValueError("max_retries must be at least 1")
        self.config = config
        self.max_retries = max_retries
        self.retry_backoff_s = (0.0 if timeout <= 1.0 else 0.5) if retry_backoff_s is None else max(0.0, retry_backoff_s)
        self._client = httpx.Client(
            base_url=config.base_url,
            auth=(config.email, config.api_token),
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            timeout=timeout,
            follow_redirects=False,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "JiraClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _raise_for_auth(self, response: httpx.Response, action: str) -> None:
        if response.status_code in {401, 403}:
            raise RuntimeError(f"Jira {action} authorization failed (HTTP {response.status_code})")

    def _raise_unavailable(self, response: httpx.Response | None, path: str, exc: Exception | None = None) -> None:
        target = f"{self.config.base_url}{path}"
        if response is not None:
            body_preview = response.text[:500] if response.text else ""
            hint = ""
            if "Product Unavailable" in body_preview or "Page Unavailable" in body_preview:
                hint = " (Atlassian Cloud reports Product/Page Unavailable — verify the Jira site is active)"
            raise JiraServiceUnavailableError(
                f"Jira service unavailable at {target} (HTTP {response.status_code}){hint}",
                status_code=response.status_code,
                url=target,
            )
        raise JiraServiceUnavailableError(
            f"Jira service unreachable at {target}: {exc}",
            status_code=None,
            url=target,
        ) from exc

    def _get_with_retry(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        action: str = "authentication",
    ) -> httpx.Response:
        last_response: httpx.Response | None = None
        last_exc: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                response = self._client.get(path, params=params)
            except httpx.TransportError as exc:
                last_exc = exc
                if attempt < self.max_retries and self.retry_backoff_s > 0:
                    time.sleep(self.retry_backoff_s * attempt)
                continue
            self._raise_for_auth(response, action)
            if response.status_code in _RETRYABLE_STATUS_CODES:
                last_response = response
                if attempt < self.max_retries and self.retry_backoff_s > 0:
                    time.sleep(self.retry_backoff_s * attempt)
                continue
            response.raise_for_status()
            return response
        self._raise_unavailable(last_response, path, last_exc)
        raise AssertionError("unreachable")  # pragma: no cover

    def verify_access(self) -> JiraProjectResult:
        response = self._get_with_retry(f"/rest/api/3/project/{self.config.project_key}")
        payload = response.json()
        return JiraProjectResult(
            str(payload.get("key", "")),
            str(payload.get("name", "")),
            str(payload.get("projectTypeKey", "")),
        )

    def find_project_issues(self, max_results: int = 1000) -> dict[str, JiraIssueResult]:
        """Return project issues keyed by exact summary, with paginated retrieval."""
        result: dict[str, JiraIssueResult] = {}
        start_at = 0
        page_size = min(max_results, 100)
        while len(result) < max_results:
            response = self._get_with_retry(
                "/rest/api/3/search/jql",
                params={
                    "jql": f"project = {self.config.project_key}",
                    "maxResults": page_size,
                    "startAt": start_at,
                    "fields": "summary,labels",
                },
            )
            payload = response.json()
            issues = payload.get("issues", [])
            if not isinstance(issues, list):
                raise RuntimeError("Unexpected Jira issue-search payload")
            for item in issues:
                key = str(item.get("key", ""))
                summary = str(item.get("fields", {}).get("summary", ""))
                if not key or not summary:
                    continue
                if summary in result and result[summary].key != key and (summary.startswith("[SAQA-") or summary.startswith("SAQA |")):
                    raise RuntimeError(
                        f"Jira has duplicate managed summary: {summary!r} ({result[summary].key}, {key})"
                    )
                result[summary] = JiraIssueResult(key, str(item.get("id", "")), f"{self.config.base_url}/browse/{key}")
            if not issues or len(issues) < page_size:
                break
            start_at += len(issues)
        return result

    def search_issues(self, jql: str, max_results: int = 100) -> list[JiraIssueResult]:
        """Search Jira issues using an explicit JQL query."""
        response = self._get_with_retry(
            "/rest/api/3/search/jql",
            params={"jql": jql, "maxResults": max_results, "fields": "summary"},
        )
        return [
            JiraIssueResult(
                str(item["key"]),
                str(item["id"]),
                f"{self.config.base_url}/browse/{item['key']}",
            )
            for item in response.json().get("issues", [])
            if item.get("key")
        ]

    def find_bootstrap_issues(self) -> dict[str, JiraIssueResult]:
        """Return existing SAQA bootstrap work items, keyed by exact summary."""
        response = self._get_with_retry(
            "/rest/api/3/search/jql",
            params={
                "jql": f"project = {self.config.project_key} AND labels = saqa-bootstrap",
                "maxResults": 100,
                "fields": "summary",
            },
        )
        issues = response.json().get("issues", [])
        return {
            str(i["fields"]["summary"]): JiraIssueResult(
                str(i["key"]),
                str(i["id"]),
                f"{self.config.base_url}/browse/{i['key']}",
            )
            for i in issues
            if i.get("key") and i.get("fields", {}).get("summary")
        }

    def get_issue_state(self, issue_key: str) -> JiraIssueState:
        response = self._get_with_retry(
            f"/rest/api/3/issue/{issue_key}",
            params={"fields": "status,labels"},
        )
        fields = response.json().get("fields", {})
        status = fields.get("status") or {}
        return JiraIssueState(
            key=issue_key,
            status=str(status.get("name", "")),
            labels=tuple(str(label) for label in fields.get("labels", []) or []),
        )

    def get_issue_comments(self, issue_key: str, max_pages: int = 20) -> list[dict[str, Any]]:
        """Return recent Jira comments across pages so marker checks are complete."""
        comments: list[dict[str, Any]] = []
        start_at = 0
        for _ in range(max_pages):
            response = self._get_with_retry(
                f"/rest/api/3/issue/{issue_key}/comment",
                params={"startAt": start_at, "maxResults": 100, "orderBy": "-created"},
            )
            payload = response.json()
            batch = payload.get("comments", [])
            if not isinstance(batch, list):
                raise RuntimeError(f"Unexpected Jira comments payload for {issue_key}")
            comments.extend(item for item in batch if isinstance(item, dict))
            total = int(payload.get("total", len(comments)))
            if not batch or len(comments) >= total:
                break
            start_at += len(batch)
        return comments

    def create_task(self, summary: str, description: str, labels: list[str]) -> JiraIssueResult:
        return self._create_issue("Task", summary, description, labels)

    def create_bug(self, summary: str, description: str, labels: list[str]) -> JiraIssueResult:
        """Create a Jira Bug with explicit automation traceability."""
        return self._create_issue("Bug", summary, description, labels)

    def _create_issue(self, issue_type: str, summary: str, description: str, labels: list[str]) -> JiraIssueResult:
        payload: dict[str, Any] = {"fields": {
            "project": {"key": self.config.project_key},
            "issuetype": {"name": issue_type},
            "summary": summary,
            "description": {
                "type": "doc",
                "version": 1,
                "content": [{
                    "type": "paragraph",
                    "content": [{"type": "text", "text": description}],
                }],
            },
            "labels": labels,
        }}
        response = self._client.post("/rest/api/3/issue", json=payload)
        self._raise_for_auth(response, "write")
        response.raise_for_status()
        result = response.json()
        key = str(result["key"])
        return JiraIssueResult(key, str(result["id"]), f"{self.config.base_url}/browse/{key}")

    def update_labels(self, issue_key: str, *, add: Iterable[str] = (), remove: Iterable[str] = ()) -> None:
        update: dict[str, list[dict[str, str]]] = {"labels": []}
        for label in add:
            update["labels"].append({"add": label})
        for label in remove:
            update["labels"].append({"remove": label})
        if not update["labels"]:
            return
        response = self._client.put(f"/rest/api/3/issue/{issue_key}", json={"update": update})
        self._raise_for_auth(response, "write")
        response.raise_for_status()

    def add_comment_once(self, issue_key: str, body: str, marker: str) -> bool:
        """Add an ADF comment only if the deterministic marker is not present."""
        for comment in self.get_issue_comments(issue_key):
            if marker in str(comment):
                return False
        payload = {
            "body": {
                "type": "doc",
                "version": 1,
                "content": [{
                    "type": "paragraph",
                    "content": [{"type": "text", "text": body}],
                }],
            }
        }
        response = self._client.post(f"/rest/api/3/issue/{issue_key}/comment", json=payload)
        self._raise_for_auth(response, "comment")
        response.raise_for_status()
        return True

    def transition_to_any(self, issue_key: str, target_statuses: Iterable[str]) -> str | None:
        """Transition only when Jira exposes an exact matching available destination status."""
        response = self._get_with_retry(f"/rest/api/3/issue/{issue_key}/transitions")
        wanted = {status.casefold() for status in target_statuses}
        current = self.get_issue_state(issue_key).status
        for transition in response.json().get("transitions", []):
            destination = str((transition.get("to") or {}).get("name", ""))
            if destination.casefold() in wanted:
                if current.casefold() == destination.casefold():
                    return destination
                transition_id = str(transition.get("id", ""))
                if not transition_id:
                    continue
                transition_response = self._client.post(
                    f"/rest/api/3/issue/{issue_key}/transitions",
                    json={"transition": {"id": transition_id}},
                )
                self._raise_for_auth(transition_response, "transition write")
                transition_response.raise_for_status()
                return destination
        return None

    def get_myself_account_id(self) -> str | None:
        """Return the authenticated Jira user's accountId when available."""
        response = self._get_with_retry("/rest/api/3/myself")
        account_id = response.json().get("accountId")
        return str(account_id) if account_id else None

    def create_epic(
        self,
        summary: str,
        description_adf: Mapping[str, Any],
        labels: list[str],
        *,
        start_date: str | None = None,
        due_date: str | None = None,
        assignee_id: str | None = None,
    ) -> JiraIssueResult:
        """Create a Jira Epic for Timeline / Roadmap grouping."""
        fields: dict[str, Any] = {
            "project": {"key": self.config.project_key},
            "issuetype": {"name": "Epic"},
            "summary": summary,
            "description": dict(description_adf),
            "labels": labels,
        }
        if start_date:
            fields["customfield_10015"] = start_date
        if due_date:
            fields["duedate"] = due_date
        if assignee_id:
            fields["assignee"] = {"accountId": assignee_id}
        response = self._client.post("/rest/api/3/issue", json={"fields": fields})
        self._raise_for_auth(response, "epic write")
        response.raise_for_status()
        result = response.json()
        key = str(result["key"])
        return JiraIssueResult(key, str(result["id"]), f"{self.config.base_url}/browse/{key}")

    def update_issue_fields(self, issue_key: str, fields: Mapping[str, Any]) -> None:
        """Update rich issue fields (description ADF, timeline dates, parent epic, priority, environment)."""
        if not fields:
            return
        response = self._client.put(f"/rest/api/3/issue/{issue_key}", json={"fields": dict(fields)})
        self._raise_for_auth(response, "field update")
        response.raise_for_status()

    def add_adf_comment_once(self, issue_key: str, adf_doc: Mapping[str, Any], marker: str) -> bool:
        """Add a rich Atlassian Document Format (ADF) comment only if marker is not present."""
        for comment in self.get_issue_comments(issue_key):
            if marker in str(comment):
                return False
        response = self._client.post(
            f"/rest/api/3/issue/{issue_key}/comment",
            json={"body": dict(adf_doc)},
        )
        self._raise_for_auth(response, "comment")
        response.raise_for_status()
        return True

    def upload_attachment(
        self,
        issue_key: str,
        file_path: Path,
        *,
        replace_existing: bool = True,
    ) -> dict[str, Any] | None:
        """Attach a report or evidence file directly to a Jira issue."""
        if not file_path.is_file():
            return None
        if replace_existing:
            issue_resp = self._get_with_retry(
                f"/rest/api/3/issue/{issue_key}",
                params={"fields": "attachment"},
            )
            attachments = (issue_resp.json().get("fields") or {}).get("attachment") or []
            for att in attachments:
                if isinstance(att, dict) and att.get("filename") == file_path.name and att.get("id"):
                    self._client.delete(f"/rest/api/3/attachment/{att['id']}")

        content = file_path.read_bytes()
        response = httpx.post(
            f"{self.config.base_url}/rest/api/3/issue/{issue_key}/attachments",
            auth=(self.config.email, self.config.api_token),
            headers={
                "Accept": "application/json",
                "X-Atlassian-Token": "no-check",
            },
            files={"file": (file_path.name, content)},
            timeout=30.0,
        )
        self._raise_for_auth(response, "attachment upload")
        response.raise_for_status()
        payload = response.json()
        if isinstance(payload, list) and payload:
            return dict(payload[0])
        return None


def verify_from_env() -> JiraProjectResult:
    with JiraClient(JiraConfig.from_env()) as client:
        return client.verify_access()
