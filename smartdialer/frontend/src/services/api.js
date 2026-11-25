// In dev, vite.config.js proxies these same paths straight to the FastAPI
// backend on :8000 (no rewrite needed -- the paths match 1:1). In production,
// FastAPI serves this built frontend itself from the same origin, so these
// calls hit its routes directly with no proxy involved either way.
const BASE = "";

async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status}: ${text}`);
  }
  return res.json();
}

export const api = {
  seed: (num_agents, num_borrowers) =>
    request("/seed", { method: "POST", body: JSON.stringify({ num_agents, num_borrowers }) }),
  reset: () => request("/simulation/reset", { method: "POST" }),
  tick: (mode, provider, answer_rate) =>
    request("/simulation/tick", { method: "POST", body: JSON.stringify({ mode, provider, answer_rate }) }),
  dashboard: () => request("/dashboard"),
  demoDuplicate: () => request("/demo/duplicate-event", { method: "POST" }),
  demoOutOfOrder: () => request("/demo/out-of-order-event", { method: "POST" }),
  demoWorkerCrash: () => request("/demo/worker-crash", { method: "POST" }),
  demoProviderOutage: () => request("/demo/provider-outage", { method: "POST" }),
  demoAgentDropout: () => request("/demo/agent-dropout", { method: "POST" }),
};
