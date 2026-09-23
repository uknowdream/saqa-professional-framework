# k6 Performance Gate

SAQA adds k6 as a separate performance executor while retaining the existing deterministic Python performance gate.

Reference test: GET /rest/products/search?q=apple, 5 virtual users, 20 seconds, http_req_failed < 1%, p95 response time < 1000 ms.

The executor is read-only and targets only the local/containerized Juice Shop service.

Local execution:
make install
docker run --detach --rm --name saqa-juice-shop-k6 -p 127.0.0.1:3000:3000 bkimminich/juice-shop:v20.2.0
for attempt in {1..30}; do curl --silent --fail --max-time 5 http://127.0.0.1:3000/ >/dev/null && break; sleep 2; done
python scripts/k6_gate.py
docker stop saqa-juice-shop-k6

The k6 container uses host networking to reach the loopback-bound authorized target on the GitHub runner.
