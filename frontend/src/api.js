const API_BASE = (import.meta.env.VITE_API_URL || "").replace(/\/$/, "");

export async function apiRequest(path, options = {}) {
  const response = await fetch(`${API_BASE}/api${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers || {}) }
  });
  const bodyText = await response.text();
  let body = null;
  try { body = bodyText ? JSON.parse(bodyText) : null; } catch { body = bodyText; }
  if (!response.ok) {
    const message = body?.error?.message || body?.message || `${response.status} ${response.statusText}`;
    throw new Error(message);
  }
  return body;
}

export const getHealth = () => apiRequest("/health");
export const getMeta = () => apiRequest("/meta");
export const getExamples = () => apiRequest("/examples");
export const getExperiments = () => apiRequest("/experiments");
export const runBacktest = (payload) => apiRequest("/backtest", {
  method: "POST",
  body: JSON.stringify(payload)
});

export const generateAlphaIdeas = (payload) => apiRequest("/generate-alpha", { method: "POST", body: JSON.stringify(payload) });
