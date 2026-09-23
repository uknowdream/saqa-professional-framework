#!/usr/bin/env python3
"""Reconcile Jira against one common latest completed SAQA commit on main."""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
import urllib.parse
import urllib.request

WORKFLOWS = ("SAQA CI", "SAQA Contract Testing", "SAQA Accessibility", "SAQA Mobile Readiness", "SAQA k6 Performance")


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


def workflow_ids() -> dict[str, int]:
    repo = os.environ["GITHUB_REPOSITORY"]
    payload = gh_get(f"/repos/{repo}/actions/workflows?per_page=100")
    workflows = payload.get("workflows", []) if isinstance(payload, dict) else []
    result: dict[str, int] = {}
    for item in workflows:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", ""))
        if name in WORKFLOWS and item.get("id") is not None:
            result[name] = int(item["id"])
    missing = [name for name in WORKFLOWS if name not in result]
    if missing:
        raise SystemExit(f"Unable to resolve mandatory workflow IDs: {', '.join(missing)}")
    return result


def completed_runs(workflow_name: str, workflow_id: int, max_pages: int = 20) -> list[dict[str, object]]:
    repo = os.environ["GITHUB_REPOSITORY"]
    runs: list[dict[str, object]] = []
    for page in range(1, max_pages + 1):
        query = urllib.parse.urlencode({"branch": "main", "status": "completed", "per_page": 100, "page": page})
        payload = gh_get(f"/repos/{repo}/actions/workflows/{workflow_id}/runs?{query}")
        batch = payload.get("workflow_runs", []) if isinstance(payload, dict) else []
        if not isinstance(batch, list):
            break
        typed = [run for run in batch if isinstance(run, dict)]
        runs.extend(typed)
        if len(typed) < 100:
            break
    return [
        run for run in runs
        if run.get("status") == "completed" and run.get("head_branch") == "main" and run.get("head_sha")
    ]


def main_history(max_pages: int = 20) -> list[str]:
    repo = os.environ["GITHUB_REPOSITORY"]
    history: list[str] = []
    for page in range(1, max_pages + 1):
        query = urllib.parse.urlencode({"sha": "main", "per_page": 100, "page": page})
        payload = gh_get(f"/repos/{repo}/commits?{query}")
        batch = payload if isinstance(payload, list) else []
        typed = [str(item["sha"]) for item in batch if isinstance(item, dict) and item.get("sha")]
        history.extend(typed)
        if len(typed) < 100:
            break
    return history


def select_common_run() -> dict[str, dict[str, object]] | None:
    ids = workflow_ids()
    by_workflow = {name: completed_runs(name, ids[name]) for name in WORKFLOWS}
    sha_sets = [{str(run["head_sha"]) for run in runs} for runs in by_workflow.values()]
    common = set.intersection(*sha_sets) if sha_sets else set()
    if not common:
        return None

    # Certification/reconciliation follows the repository's main ancestry, not
    # wall-clock completion time. An older rerun must never overwrite newer state.
    for sha in main_history():
        if sha not in common:
            continue
        selected = {}
        for name in WORKFLOWS:
            candidates = [run for run in by_workflow[name] if str(run["head_sha"]) == sha]
            if not candidates:
                raise SystemExit(f"Internal reconciliation error: no run for {name} on {sha}")
            selected[name] = max(candidates, key=lambda run: int(run.get("id", 0)))
        return selected
    return None


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

    selected_runs = list(selected.values())
    all_runs = {"workflow_runs": selected_runs}
    for workflow_name in WORKFLOWS:
        run = selected[workflow_name]
        run_id = str(run["id"])
        jobs = gh_get(f"/repos/{repo}/actions/runs/{run_id}/jobs?per_page=100")
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
            subprocess.run(["python3", "scripts/sync_jira_ci.py"], env=env, check=True)
            print(f"{workflow_name}: reconciled run {run_id} on {common_sha}")


if __name__ == "__main__":
    main()
