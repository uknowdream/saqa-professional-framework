import http from "k6/http";
import { check, sleep } from "k6";
export const options = { vus: 5, duration: "20s", thresholds: { http_req_failed: ["rate<0.01"], http_req_duration: ["p(95)<1000"] } };
export default function () {
  const response = http.get("http://127.0.0.1:3000/rest/products/search?q=apple", { tags: { endpoint: "products-search" } });
  check(response, {
    "status is 200": (r) => r.status === 200,
    "content type is JSON": (r) => String(r.headers["Content-Type"] || "").toLowerCase().includes("application/json"),
  });
  sleep(0.2);
}
