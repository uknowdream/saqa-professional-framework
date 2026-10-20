import { get } from "k6/http";
import { check, sleep } from "k6";

export const options = {
  vus: 5,
  duration: "20s",
  summaryTrendStats: ["avg", "min", "med", "max", "p(90)", "p(95)", "p(99)"],
  thresholds: {
    http_req_failed: ["rate<=0.01"],
    http_req_duration: ["p(95)<=1000", "p(99)<=1500"],
    checks: ["rate==1.00"],
  },
};

export default function () {
  const response = get("http://127.0.0.1:3000/rest/products/search?q=apple", {
    tags: { endpoint: "products-search" },
  });
  check(response, {
    "status is 200": (r) => r.status === 200,
    "content type is JSON": (r) =>
      String(r.headers["Content-Type"] || "").toLowerCase().includes("application/json"),
  });
  sleep(0.2);
}

// Export an explicit, stable summary shape instead of relying on the legacy
// --summary-export serializer, which omitted percentile keys in CI.
export function handleSummary(data) {
  const metrics = data.metrics || {};
  const pick = (name) => {
    const metric = metrics[name];
    return metric && metric.values ? { values: metric.values } : undefined;
  };
  const summary = {
    schema: "saqa.k6-summary.v1",
    metrics: {
      http_req_duration: pick("http_req_duration"),
      http_req_failed: pick("http_req_failed"),
      http_reqs: pick("http_reqs"),
      checks: pick("checks"),
    },
  };
  return {
    "/artifacts/k6-summary.json": JSON.stringify(summary, null, 2) + "\n",
  };
}
