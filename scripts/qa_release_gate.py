#!/usr/bin/env python3
"""Fail-closed release certification from exact GitHub Actions evidence."""
from __future__ import annotations
import json,os
from dataclasses import dataclass
from pathlib import Path

MANDATORY=("SAQA CI","SAQA Contract Testing","SAQA Accessibility","SAQA Mobile Readiness","SAQA k6 Performance")
@dataclass(frozen=True,slots=True)
class Decision:
    status:str
    reason:str

def normalize_runs(raw:object)->list[dict[str,str]]:
    if isinstance(raw,dict): raw=raw.get("workflow_runs",[])
    if not isinstance(raw,list): return []
    out=[]
    for item in raw:
        if not isinstance(item,dict): continue
        run_id=str(item.get("id",""))
        if not run_id.isdigit() or int(run_id)<=0: continue
        out.append({"name":str(item.get("name","")),"status":str(item.get("status","")),"conclusion":str(item.get("conclusion") or ""),"head_sha":str(item.get("head_sha","")),"head_branch":str(item.get("head_branch","")),"event":str(item.get("event","")),"run_id":run_id,"url":str(item.get("html_url",""))})
    return out

def result(run:dict[str,str]|None)->str:
    if not run:return "UNVERIFIED"
    if run["status"]!="completed":return "PENDING"
    if run["conclusion"]=="success":return "PASS"
    if run["conclusion"] in {"failure","timed_out","startup_failure"}:return "FAIL"
    if run["conclusion"] in {"cancelled","action_required","stale"}:return "BLOCKED"
    return "UNVERIFIED"

def decide(results:dict[str,str])->Decision:
    if any(results.get(n)=="FAIL" for n in MANDATORY):return Decision("NOT_CERTIFIED","A mandatory quality domain failed.")
    if any(results.get(n)=="BLOCKED" for n in MANDATORY):return Decision("NOT_CERTIFIED","A mandatory quality domain is blocked.")
    if any(results.get(n)=="PENDING" for n in MANDATORY):return Decision("NOT_CERTIFIED","Mandatory evidence is still pending.")
    if any(results.get(n)!="PASS" for n in MANDATORY):return Decision("NOT_CERTIFIED","Mandatory evidence is missing or unverified.")
    return Decision("CERTIFIED","All mandatory quality domains have verified PASS evidence.")

def select_runs(raw:object,sha:str,event:str|None=None)->list[dict[str,str]]:
    return [run for run in normalize_runs(raw) if run["head_sha"]==sha and (not event or run["event"]==event)]

def main()->int:
    path=Path(os.environ.get("SAQA_RUNS_JSON",""))
    if not path.is_file():raise SystemExit("SAQA_RUNS_JSON must point to a GitHub Actions runs JSON file")
    sha=os.environ.get("SAQA_HEAD_SHA","").strip()
    if len(sha)!=40 or any(ch not in "0123456789abcdefABCDEF" for ch in sha):raise SystemExit("SAQA_HEAD_SHA must be a full 40-character commit SHA")
    event=os.environ.get("SAQA_REQUIRED_EVENT","").strip()
    if event and event not in {"push","pull_request","workflow_dispatch"}:raise SystemExit("SAQA_REQUIRED_EVENT must be push, pull_request, or workflow_dispatch")
    runs=select_runs(json.loads(path.read_text(encoding="utf-8")),sha,event or None)
    latest={}
    for run in runs:
        if run["name"] not in MANDATORY:continue
        prev=latest.get(run["name"])
        if prev is None or int(run["run_id"])>int(prev["run_id"]):latest[run["name"]]=run
    results={name:result(latest.get(name)) for name in MANDATORY}
    decision=decide(results)
    payload={"schema":"saqa.release-certification.v4","head_sha":sha,"required_event":event or None,"status":decision.status,"reason":decision.reason,"mandatory_domains":results,"evidence":{name:latest.get(name,{}) for name in MANDATORY}}
    output=Path(os.environ.get("SAQA_CERTIFICATION_OUTPUT","artifacts/release-certification.json")); output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(payload,indent=2,sort_keys=True)+"\n",encoding="utf-8"); print(json.dumps(payload,indent=2,sort_keys=True))
    return 0 if decision.status=="CERTIFIED" else 1

if __name__=="__main__":raise SystemExit(main())
