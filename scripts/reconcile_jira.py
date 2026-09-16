#!/usr/bin/env python3
"""Reconcile Jira against one common latest completed SAQA commit on main."""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
import urllib.parse
import urllib.request

WORKFLOWS = ("SAQA CI", "SAQA Accessibility", "SAQA Mobile Readiness")
WORKFLOW_IDS = {
    "SAQA CI": 345839221,
    "SAQA Accessibility": 355591975,
    "SAQA Mobile Readiness": 355328607,
}


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


def completed_runs(workflow_name: str, per_page: int = 100) -> list[dict[str, object]]:
    workflow_id = WORKFLOW_IDS[workflow_name]
    query = urllib.parse.urlencode({"branch": "main", "status": "completed", "per_page": per_page})
    payload = gh_get(f"/repos/{os.environ['GITHUB_REPOSITORY']}/actions/workflows/{workflow_id}/runs?{query}")
    runs = payload.get("workflow_runs", []) if isinstance(payload, dict) else []
    return [
        run for run in runs
        if isinstance(run, dict) and run.get("status") == "completed" and run.get("head_branch") == "main"
    ]


def select_common_run() -> dict[str, dict[str, object]] | None:
    by_workflow = {name: completed_runs(name) for name in WORKFLOWS}
    sha_sets = [{str(run.get("head_sha")) for run in runs if run.get("head_sha")} for runs in by_workflow.values()]
    common = set.intersection(*sha_sets) if sha_sets else set()
    if not common:
        return None

    candidates = []
    for sha in common:
        selected = {
            name: next(run for run in by_workflow[name] if str(run.get("head_sha")) == sha)
            for name in WORKFLOWS
        }
        latest_time = max(str(run.get("completed_at", "")) for run in selected.values())
        candidates.append((latest_time, sha, selected))
    candidates.sort(reverse=True)
    return candidates[0][2]


def main() -> None:
    repo = os.environ["GITHUB_REPOSITORY"]
    selected = select_common_run()
    if not selected:
        raise SystemExit("No common completed main commit has all mandatory SAQA workflow evidence")

    shas = {str(run.get("head_sha")) for run in selected.values()}
    if len(shas) != 1:
        raise SystemExit("Internal reconciliation error: selected workflows do not share one commit")
    common_sha = next(iter(shas))
    print(f"Reconciling common main commit: {common_sha}")

    for workflow_name in WORKFLOWS:
        run = selected[workflow_name]
        run_id = str(run["id"])
        jobs = gh_get(f"/repos/{repo}/actions/runs/{run_id}/jobs?per_page=100")
        all_runs = gh_get(f"/repos/{repo}/actions/runs?head_sha={urllib.parse.quote(common_sha)}&per_page=100")
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
                "JIRA_HEAD_SHA": common_sha,
                "JIRA_HEAD_BRANCH": "main",
                "JIRA_RUN_URL": str(run.get("html_url", "")),
                "JIRA_JOBS_JSON": jobs_path,
                "JIRA_ALL_RUNS_JSON": runs_path,
            })
            subprocess.run(["python", "scripts/sync_jira_ci.py"], env=env, check=True)
            print(f"{workflow_name}: reconciled run {run_id} on {common_sha}")


if __name__ == "__main__":
    main()
