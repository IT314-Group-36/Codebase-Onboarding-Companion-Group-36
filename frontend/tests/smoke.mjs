// UI smoke test: loads the real frontend in jsdom and clicks through every tab
// against a RUNNING backend (python run.py). Usage: npm install && npm test
import { readFileSync } from "node:fs";
import { JSDOM } from "jsdom";

const html = readFileSync(new URL("../index.html", import.meta.url), "utf8").replace(/<script[^>]*><\/script>/g, "");
const dom = new JSDOM(html, { url: "http://localhost:3000/", pretendToBeVisual: true });
const { window } = dom;
Object.assign(globalThis, { window, document: window.document, location: window.location, localStorage: window.localStorage });
window.CSS = globalThis.CSS = { escape: (s) => String(s).replace(/[^\w-]/g, "\\$&") };
window.HTMLElement.prototype.scrollIntoView = () => {};
window.HTMLDialogElement.prototype.showModal = function () { this.open = true; };
window.HTMLDialogElement.prototype.close = function () { this.open = false; };
window.confirm = globalThis.confirm = () => true;
window.__NO_AUTOSTART__ = true;

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
async function until(fn, what, ms = 15000) {
  const t0 = Date.now();
  while (Date.now() - t0 < ms) { try { const v = fn(); if (v) return v; } catch {} await sleep(150); }
  const v = document.querySelector("main .view.active");
  throw new Error("Timed out waiting for: " + what + "\nActive view text: " + (v ? v.textContent.replace(/\s+/g, " ").slice(0, 400) : "(none)"));
}
let failures = 0;
const ok = (cond, msg) => { console.log((cond ? "PASS " : "FAIL ") + msg); if (!cond) failures++; };
const $ = (s) => document.querySelector(s);
const active = () => $("main .view.active");
const noError = (name) => ok(!active().querySelector(".error-box"), `${name}: no error box`);

const { start } = await import("../js/main.js");
await start();

// Clean slate: delete any existing repos through the UI's API layer
const { api } = await import("../js/api.js");
for (const r of await api.listRepos()) await api.deleteRepo(r.id);
await start();
ok(!!$("#hero-demo"), "welcome screen shows demo button");

$("#hero-demo").click();
await until(() => $("#view-map .card"), "map cards after indexing");
noError("map");
ok(document.querySelectorAll("#view-map .card").length >= 5, "map shows module cards");
ok($("#health").textContent.includes("AI: connected"), "health shows AI engine connected");

// Files
document.querySelector('[data-tab="files"]').click();
await until(() => document.querySelectorAll("#f-list li[data-path]").length > 3, "file list");
[...document.querySelectorAll("#f-list li")].find((li) => li.dataset.path === "backend/app/main.py").click();
await until(() => $("#f-detail .explain"), "file explanation");
ok($("#f-detail").textContent.includes("backend/app/main.py"), "file detail shows path");
ok(document.querySelectorAll("#f-detail .ln").length > 10, "source viewer renders lines");
ok(document.querySelectorAll("#f-detail .sym-row").length >= 2, "symbols table renders");
// click a file link -> opens that file
document.querySelector("#f-detail a.file-link").click();
await until(() => $("#f-detail h2"), "linked file opens");
noError("files");

// Ask
document.querySelector('[data-tab="ask"]').click();
await until(() => $("#ask-input"), "ask view");
$("#ask-input").value = "Where is the impact analysis handled?";
$("#ask-form").dispatchEvent(new window.Event("submit", { cancelable: true, bubbles: true }));
await until(() => document.querySelectorAll("#chat .msg.bot:not(#thinking)").length >= 1 && !$("#thinking"), "answer");
ok($("#chat").textContent.includes("impact.py"), "answer mentions impact.py");
ok(document.querySelectorAll("#chat .sources a.file-link").length >= 1, "answer has source links");

// Impact
document.querySelector('[data-tab="impact"]').click();
await until(() => $("#imp-input"), "impact view");
$("#imp-input").value = "backend/app/models.py";
$("#imp-form").dispatchEvent(new window.Event("submit", { cancelable: true, bubbles: true }));
await until(() => $("#imp-result .card"), "impact result");
ok($("#imp-result").textContent.includes("risk:"), "impact shows risk");
noError("impact");

// Graph
document.querySelector('[data-tab="graph"]').click();
await until(() => $("#graph-box svg"), "graph svg");
ok(document.querySelectorAll(".gnode").length >= 5, "module graph has nodes");
document.querySelector('input[name=lvl][value=file]').click();
document.querySelector('input[name=lvl][value=file]').dispatchEvent(new window.Event("change", { bubbles: true }));
await until(() => document.querySelectorAll(".gnode[data-level=file]").length > 5, "file-level graph");
ok(true, "file-level graph renders");
const pos = [...document.querySelectorAll(".gnode")].map((g) => g.getAttribute("transform"));
ok(pos.every((t) => !t.includes("NaN")), "graph layout has no NaN positions");

// Tasks
document.querySelector('[data-tab="tasks"]').click();
await until(() => $("#view-tasks .plan .card"), "plan");
ok(document.querySelectorAll("#view-tasks .plan .card").length === 5, "5-day plan rendered");
noError("tasks");

// XSS safety: untrusted text must be escaped
const { md } = await import("../js/util.js");
ok(!md("<img src=x onerror=alert(1)>").includes("<img"), "md() escapes HTML");

console.log(failures ? `\n${failures} FAILED` : "\nAll UI checks passed");
process.exit(failures ? 1 : 0);
