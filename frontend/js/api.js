// Thin fetch wrapper around the backend REST API.

const fromQuery = typeof location !== "undefined" ? new URLSearchParams(location.search).get("api") : null;
const fromWindow = typeof window !== "undefined" ? window.API_BASE : null;
export const BASE = (fromQuery || fromWindow || "http://localhost:8000").replace(/\/$/, "");

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

async function request(method, path, body) {
  let res;
  try {
    res = await fetch(BASE + path, {
      method,
      headers: body ? { "Content-Type": "application/json" } : {},
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new ApiError(`Cannot reach the backend at ${BASE}. Is it running?`, 0);
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const j = await res.json();
      detail = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail ?? j);
    } catch { /* ignore */ }
    throw new ApiError(detail, res.status);
  }
  return res.status === 204 ? null : res.json();
}

const qs = (params = {}) => {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null && v !== "") p.set(k, v);
  const s = p.toString();
  return s ? "?" + s : "";
};
const R = (id) => `/api/v1/repos/${id}`;

export const api = {
  health: () => request("GET", "/health"),
  listRepos: () => request("GET", "/api/v1/repos"),
  createRepo: (source, name) => request("POST", "/api/v1/repos", { source, name: name || null }),
  getRepo: (id) => request("GET", R(id)),
  reindex: (id) => request("POST", `${R(id)}/reindex`),
  deleteRepo: (id) => request("DELETE", R(id)),
  map: (id) => request("GET", `${R(id)}/map`),
  files: (id, params) => request("GET", `${R(id)}/files${qs(params)}`),
  file: (id, path) => request("GET", `${R(id)}/files/${path.split("/").map(encodeURIComponent).join("/")}`),
  source: (id, path) => request("GET", `${R(id)}/source${qs({ path })}`),
  symbols: (id, params) => request("GET", `${R(id)}/symbols${qs(params)}`),
  graph: (id, level, limit) => request("GET", `${R(id)}/graph${qs({ level, limit })}`),
  ask: (id, question) => request("POST", `${R(id)}/ask`, { question }),
  questions: (id, limit = 20) => request("GET", `${R(id)}/questions${qs({ limit })}`),
  impact: (id, target) => request("POST", `${R(id)}/impact`, { target }),
  tasks: (id) => request("GET", `${R(id)}/onboarding-tasks`),
};
