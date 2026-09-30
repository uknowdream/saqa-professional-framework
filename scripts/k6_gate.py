"""Run a deterministic local k6 performance gate and normalize evidence."""
from __future__ import annotations
import json, os, subprocess, time
from datetime import datetime, timezone
from pathlib import Path

OUTPUT=Path(os.getenv("SAQA_K6_OUTPUT","artifacts/targets/juice-shop-k6.json"))
SCRIPT=Path(os.getenv("SAQA_K6_SCRIPT","performance/k6/juice-shop.js"))
CONTAINER="saqa-k6-gate"

def main()->int:
    OUTPUT.parent.mkdir(parents=True,exist_ok=True)
    started=time.perf_counter()
    evidence={"schema":"saqa.k6-gate.v2","test_id":"juice-shop.performance.k6-products-search","status":"BLOCKED","target":"http://127.0.0.1:3000","http_methods":["GET"],"destructive_actions":False,"observed_at":datetime.now(timezone.utc).isoformat(),"details":{"script":str(SCRIPT)}}
    if not SCRIPT.is_file():
        evidence["status"]="FAIL"; evidence["details"]["error"]=f"k6 script not found: {SCRIPT}"
    else:
        try:
            completed=subprocess.run(["docker","run","--name",CONTAINER,"--network","host","-v",f"{SCRIPT.parent.resolve()}:/scripts:ro","grafana/k6:1.2.0","run",f"/scripts/{SCRIPT.name}"],capture_output=True,text=True,timeout=90,check=False)
            evidence["details"].update({"exit_code":completed.returncode,"elapsed_ms":round((time.perf_counter()-started)*1000,2),"stdout_tail":completed.stdout[-4000:],"stderr_tail":completed.stderr[-4000:]})
            evidence["status"]="PASS" if completed.returncode==0 else "FAIL"
        except subprocess.TimeoutExpired as exc:
            evidence["status"]="BLOCKED"; evidence["details"].update({"error":f"TimeoutExpired: {exc}","elapsed_ms":round((time.perf_counter()-started)*1000,2)})
        except OSError as exc:
            evidence["status"]="BLOCKED"; evidence["details"]["error"]=f"{type(exc).__name__}: {exc}"
        finally:
            subprocess.run(["docker","rm","-f",CONTAINER],capture_output=True,text=True,timeout=15,check=False)
    OUTPUT.write_text(json.dumps(evidence,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps(evidence,indent=2,sort_keys=True))
    return 0 if evidence["status"]=="PASS" else 1
if __name__=="__main__": raise SystemExit(main())
