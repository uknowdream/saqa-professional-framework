"""Safe application-security regression checks for authorized loopback targets."""
from __future__ import annotations
import os
from urllib.parse import urlparse
import httpx

BASE=os.getenv("SAQA_SECURITY_TARGET","http://127.0.0.1:3000").rstrip("/")

def main()->int:
    p=urlparse(BASE)
    if p.scheme!="http" or p.hostname!="127.0.0.1" or p.port is None:
        raise SystemExit("target must be credential-free loopback HTTP")
    with httpx.Client(timeout=10,follow_redirects=False,trust_env=False) as client:
        response=client.get(BASE+"/")
    if 300 <= response.status_code < 400:
        location=response.headers.get("location","")
        lp=urlparse(location)
        if lp.hostname not in {None,"127.0.0.1"}:
            raise SystemExit("unexpected external redirect")
    print({"status":"PASS","target":BASE,"method":"GET","external_redirect":False})
    return 0
if __name__=="__main__": raise SystemExit(main())
