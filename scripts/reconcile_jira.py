#!/usr/bin/env python3
"""Reconcile Jira against the latest completed SAQA workflows on main.

This is a recovery path for missed workflow_run events and state drift. It
reuses the same idempotent synchronizer as event-driven updates.
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
import urllib.parse
import urllib.request

WORKFLOWS = ("SAQA CI", "SAQA Accessibility", "SAQA Mobile Readiness")


def gh_get(path: str) -> object:
    token = os.environ.get("GH_TOKEN")
    if not token:
        raise SystemExit("GH_TOKEN is required")
    request = urllib.request.Request(
        "https://api.github.com" + path,
        headers={"Accept": "application/vnd.github+json", "Authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def latest_completed(workflow_name: str) -> dict[str, object] | None:
    repo = os.environ["GITHUB_REPOSITORY"]
    query = urllib.parse.urlencode({"branch": "main", "status": "completed", "per_page": 20})
    payload = gh_get(f"/repos/{repo}/actions/runs?{query}")
    runs = payload.get("workflow_runs", []) if isinstance(payload, dict) else []
    candidates = [r for r in runs if r.get("name") == workflow_name and r.get("status") == "completed"]
    return candidates[0] if candidates else None


def main() -> None:
    repo = os.environ["GITHUB_REPOSITORY"]
    for workflow_name in WORKFLOWS:
        run = latest_completed(workflow_name)
        if not run:
            print(f"{workflow_name}: no completed run on main; skipped")
            continue
        run_id = str(run["id"])
        jobs = gh_get(f"/repos/{repo}/actions/runs/{run_id}/jobs?per_page=100")
        all_runs = gh_get(f"/repos/{repo}/actions/runs?head_sha={urllib.parse.quote(str(run['head_sha']))}&per_page=100")
        with tempfile.TemporaryDirectory() as directory:
            jobs_path = os.path.join(directory, "jobs.json")
            runs_path = os.path.join(directory, "runs.json")
            with open(jobs_path, "w", encoding="utf-8") as handle:
                json.dump(jobs.get("jobs", []), handle)
            with open(runs_path, "w", encoding="utf-8") as handle:
                json.dump(all_runs, handle)
            env = os.environ.copy()
            env.update({
                "JIRA_WORKFLOW_NAME": workflow_name,
                "JIRA_RUN_ID": run_id,
                "JIRA_RUN_NUMBER": str(run.get("run_number", "")),
                "JIRA_RUN_CONCLUSION": str(run.get("conclusion") or ""),
                "JIRA_RUN_STATUS": str(run.get("status") or ""),
                "JIRA_HEAD_SHA": str(run.get("head_sha", "")),
                "JIRA_HEAD_BRANCH": str(run.get("head_branch", "main")),
                "JIRA_RUN_URL": str(run.get("html_url", "")),
                "JIRA_JOBS_JSON": jobs_path,
                "JIRA_ALL_RUNS_JSON": runs_path,
            })
            subprocess.run(["python", "scripts/sync_jira_ci.py"], env=env, check=True)
            print(f"{workflow_name}: reconciled run {run_id}")


if __name__ == "__main__":
    main()
