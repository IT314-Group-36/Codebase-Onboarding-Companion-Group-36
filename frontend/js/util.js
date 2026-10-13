// Small DOM / formatting helpers shared by all views.

export const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

/** Escape, then allow `inline code` and line breaks. Safe for untrusted text. */
export function md(text) {
  return esc(text).replace(/`([^`]+)`/g, "<code>$1</code>").replace(/\n/g, "<br>");
}

export function fileLink(path, line) {
  const l = line ? ` data-line="${esc(line)}"` : "";
  return `<a href="#" class="file-link" data-path="${esc(path)}"${l}>${esc(path)}${line ? ":" + esc(line) : ""}</a>`;
}

export function toast(message, kind = "info") {
  const host = document.getElementById("toasts");
  if (!host) return;
  const el = document.createElement("div");
  el.className = `toast ${kind}`;
  el.textContent = message;
  host.appendChild(el);
  setTimeout(() => el.remove(), 4500);
}

export function debounce(fn, ms = 250) {
  let t;
  return (...args) => {
    clearTimeout(t);
    t = setTimeout(() => fn(...args), ms);
  };
}

/** Run an async renderer; show the error inside the view instead of failing silently. */
export async function safe(root, fn) {
  try {
    await fn();
  } catch (e) {
    root.innerHTML = `<div class="error-box"><strong>Something went wrong.</strong><br>${esc(e.message || e)}</div>`;
  }
}

export function badge(text, kind = "") {
  return `<span class="badge ${esc(kind)}">${esc(text)}</span>`;
}

export function colorFor(name) {
  let h = 0;
  for (const ch of String(name)) h = (h * 31 + ch.charCodeAt(0)) % 360;
  return `hsl(${h} 60% 50%)`;
}

/** Label for who produced an answer: "gemini" (LLM), "offline" (engine heuristics) or none (keyword search). */
export function providerBadge(provider) {
  if (!provider) return badge("keyword search", "muted");
  if (provider === "gemini") return badge("AI · Gemini", "good");
  if (provider === "offline") return badge("AI engine · offline heuristics", "muted");
  return badge("AI · " + provider, "good");
}
