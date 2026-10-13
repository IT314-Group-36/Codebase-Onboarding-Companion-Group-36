// App shell: repo picker, tabs, health, indexing status polling, view routing.
import { api } from "./api.js";
import { $, $$, esc, fileLink, safe, toast } from "./util.js";
import * as map from "./views/map.js";
import * as files from "./views/files.js";
import * as ask from "./views/ask.js";
import * as impact from "./views/impact.js";
import * as graph from "./views/graph.js";
import * as tasks from "./views/tasks.js";

const views = { map, files, ask, impact, graph, tasks };
const TABS = Object.keys(views);
const state = { repos: [], repo: null, tab: "map", pending: {}, pollTimer: null };

const store = {
  get: (k) => { try { return localStorage.getItem(k); } catch { return null; } },
  set: (k, v) => { try { localStorage.setItem(k, v); } catch { /* ignore */ } },
};

// Context handed to every view
const ctx = {
  api,
  toast,
  get repo() { return state.repo; },
  takePending(key) { const v = state.pending[key]; delete state.pending[key]; return v; },
  openFile(path, line) { state.pending.file = { path, line }; switchTab("files"); },
  openModule(name) { state.pending.module = name; switchTab("files"); },
  openImpact(target) { state.pending.impact = target; switchTab("impact"); },
};

// ---------------------------------------------------------------- rendering
function showOnly(id) {
  $$("main .view").forEach((v) => v.classList.toggle("active", v.id === id));
}

function renderWelcome() {
  showOnly("view-welcome");
  $("#view-welcome").innerHTML = `
    <div class="hero">
      <h1>Get up to speed on any codebase, fast.</h1>
      <p>Add a repository to get a module map, plain-English file explanations, answers to
         “where is X handled?”, “what breaks if I change this?”, and a first-week plan.</p>
      <p><button class="btn primary big" id="hero-demo">▶ Index this project as a demo</button>
         <button class="btn big" id="hero-add">Add your own repository</button></p>
      <p class="muted small">The demo indexes <code>..</code> (the backend, AI engine and frontend you are running right now).</p>
    </div>`;
  $("#hero-demo").addEventListener("click", () => createRepo("..", "onboarding-companion"));
  $("#hero-add").addEventListener("click", () => $("#add-dialog").showModal());
}

function renderStatus() {
  showOnly("view-status");
  const r = state.repo;
  $("#view-status").innerHTML = r.status === "failed"
    ? `<div class="error-box"><strong>Indexing failed for ${esc(r.name)}.</strong><br>${esc(r.error || "Unknown error")}
         <p><button class="btn" id="retry">Retry</button></p></div>`
    : `<div class="hero"><div class="spinner"></div><h2>Indexing ${esc(r.name)}…</h2>
         <p class="muted">Status: ${esc(r.status)}. This page updates automatically.</p></div>`;
  $("#retry")?.addEventListener("click", reindex);
}

async function render() {
  $$("#tabs button").forEach((b) => b.classList.toggle("active", b.dataset.tab === state.tab));
  $("#tabs").classList.toggle("hidden", !state.repo || state.repo.status !== "ready");
  for (const id of ["btn-reindex", "btn-delete"]) $("#" + id).disabled = !state.repo;

  if (!state.repo) return renderWelcome();
  if (state.repo.status !== "ready") return renderStatus();

  showOnly(`view-${state.tab}`);
  const root = $(`#view-${state.tab}`);
  await safe(root, () => views[state.tab].mount(root, ctx));
}

function renderRepoSelect() {
  const sel = $("#repo-select");
  sel.innerHTML = state.repos.length
    ? state.repos.map((r) => `<option value="${r.id}" ${state.repo && r.id === state.repo.id ? "selected" : ""}>${esc(r.name)} (${esc(r.status)})</option>`).join("")
    : `<option value="">No repositories yet</option>`;
}

// ---------------------------------------------------------------- actions
export function switchTab(tab) {
  if (!TABS.includes(tab)) return;
  state.tab = tab;
  render();
}

async function refreshRepos(selectId) {
  state.repos = await api.listRepos();
  const wanted = selectId ?? state.repo?.id ?? Number(store.get("repoId"));
  state.repo = state.repos.find((r) => r.id === wanted) || state.repos[0] || null;
  if (state.repo) store.set("repoId", String(state.repo.id));
  renderRepoSelect();
  schedulePoll();
}

function schedulePoll() {
  clearTimeout(state.pollTimer);
  if (!state.repo || !["pending", "indexing"].includes(state.repo.status)) return;
  state.pollTimer = setTimeout(async () => {
    try {
      const fresh = await api.getRepo(state.repo.id);
      const changed = fresh.status !== state.repo.status;
      Object.assign(state.repo, fresh);
      const i = state.repos.findIndex((r) => r.id === fresh.id);
      if (i >= 0) state.repos[i] = state.repo;
      renderRepoSelect();
      if (changed) {
        if (fresh.status === "ready") toast(`Indexed ${fresh.name}: ${fresh.file_count} files`, "ok");
        if (fresh.status === "failed") toast(`Indexing failed: ${fresh.error}`, "error");
        render();
      }
    } catch { /* backend hiccup: keep polling */ }
    schedulePoll();
  }, 1200);
}

async function createRepo(source, name) {
  try {
    const repo = await api.createRepo(source, name);
    toast("Indexing started…");
    await refreshRepos(repo.id);
    state.tab = "map";
    render();
  } catch (e) {
    toast(e.message, "error");
  }
}

async function reindex() {
  if (!state.repo) return;
  try {
    await api.reindex(state.repo.id);
    await refreshRepos(state.repo.id);
    render();
  } catch (e) { toast(e.message, "error"); }
}

async function deleteRepo() {
  if (!state.repo || !confirm(`Delete "${state.repo.name}" and all its indexed data?`)) return;
  try {
    await api.deleteRepo(state.repo.id);
    state.repo = null;
    await refreshRepos();
    render();
  } catch (e) { toast(e.message, "error"); }
}

async function loadHealth() {
  const el = $("#health");
  try {
    const h = await api.health();
    el.innerHTML = `<span class="dot ok"></span>API · DB: ${esc(h.dialect)} · AI: ${h.ai_engine.startsWith("connected") ? "connected" : "fallback"}`;
    el.title = h.ai_engine;
  } catch {
    el.innerHTML = `<span class="dot bad"></span>Backend offline`;
  }
}

// ---------------------------------------------------------------- wiring
function wire() {
  $("#tabs").addEventListener("click", (e) => {
    const b = e.target.closest("button[data-tab]");
    if (b) switchTab(b.dataset.tab);
  });
  $("#repo-select").addEventListener("change", (e) => {
    state.repo = state.repos.find((r) => String(r.id) === e.target.value) || null;
    if (state.repo) store.set("repoId", String(state.repo.id));
    schedulePoll();
    render();
  });
  $("#btn-add-repo").addEventListener("click", () => $("#add-dialog").showModal());
  $("#btn-reindex").addEventListener("click", reindex);
  $("#btn-delete").addEventListener("click", deleteRepo);
  $("#add-cancel").addEventListener("click", () => $("#add-dialog").close());
  $("#add-form").addEventListener("submit", () => {
    const source = $("#add-source").value.trim();
    const name = $("#add-name").value.trim();
    $("#add-dialog").close();
    if (source) createRepo(source, name);
  });
  // Any file link anywhere opens the file viewer
  document.addEventListener("click", (e) => {
    const a = e.target.closest("a.file-link");
    if (!a) return;
    e.preventDefault();
    ctx.openFile(a.dataset.path, a.dataset.line);
  });
}

export async function start() {
  wire();
  loadHealth();
  setInterval(loadHealth, 30000);
  try {
    await refreshRepos();
  } catch (e) {
    toast(e.message, "error");
    state.repos = [];
  }
  await render();
}

if (typeof window !== "undefined" && !window.__NO_AUTOSTART__) start();
