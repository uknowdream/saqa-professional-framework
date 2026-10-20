import { check, sleep } from "k6";
import http from "k6/http";

// Optional exploratory profiles. The mandatory release gate remains
// performance/k6/juice-shop.js and uses its separately versioned policy.
const BASE_URL = __ENV.SAQA_K6_BASE_URL || "http://127.0.0.1:3000";
const PROFILE = __ENV.SAQA_K6_PROFILE || "load";

if (!/^http:\/\/127\.0\.0\.1:\d+$/.test(BASE_URL)) {
  throw new Error("SAQA exploratory profiles only permit credential-free HTTP on 127.0.0.1 with an explicit port");
}

const PROFILES = {
  smoke: [{ duration: "10s", target: 1 }],
  load: [
    { duration: "30s", target: 10 },
    { duration: "60s", target: 25 },
    { duration: "30s", target: 10 },
    { duration: "10s", target: 0 },
  ],
  stress: [
    { duration: "30s", target: 25 },
    { duration: "60s", target: 50 },
    { duration: "60s", target: 75 },
    { duration: "30s", target: 0 },
  ],
  spike: [
    { duration: "20s", target: 5 },
    { duration: "10s", target: 50 },
    { duration: "40s", target: 5 },
    { duration: "10s", target: 0 },
  ],
  soak: [
    { duration: "1m", target: 10 },
    { duration: "15m", target: 10 },
    { duration: "1m", target: 0 },
  ],
};

if (!Object.prototype.hasOwnProperty.call(PROFILES, PROFILE)) {
  throw new Error("Unsupported SAQA_K6_PROFILE: " + PROFILE + ". Choose: " + Object.keys(PROFILES).join(", "));
}

export const options = {
  stages: PROFILES[PROFILE],
  summaryTrendStats: ["avg", "min", "med", "max", "p(90)", "p(95)", "p(99)"],
  thresholds: {
    http_req_failed: ["rate<=0.01"],
    http_req_duration: ["p(95)<=1000", "p(99)<=1500"],
    checks: ["rate>=1.00"],
  },
  tags: { profile: PROFILE },
};

export default function () {
  const response = http.get(BASE_URL + "/rest/products/search?q=apple", {
    tags: { endpoint: "products-search", profile: PROFILE },
  });
  check(response, {
    "status is 200": (r) => r.status === 200,
    "content type is JSON": (r) =>
      String(r.headers["Content-Type"] || "").toLowerCase().includes("application/json"),
  });
  sleep(0.2);
}
