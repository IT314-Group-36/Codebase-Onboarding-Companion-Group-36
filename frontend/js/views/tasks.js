import { badge, esc, safe } from "../util.js";

function loadChecks(key) {
  try { return JSON.parse(localStorage.getItem(key) || "{}"); } catch { return {}; }
}
function saveChecks(key, v) {
  try { localStorage.setItem(key, JSON.stringify(v)); } catch { /* ignore */ }
}

export async function mount(root, ctx) {
  root.innerHTML = `<p class="muted">Building your first-week plan…</p>`;
  await safe(root, async () => {
    const data = await ctx.api.tasks(ctx.repo.id);
    const key = `plan-${ctx.repo.id}`;
    const checks = loadChecks(key);
    root.innerHTML = `
      <h2>Your first week</h2>
      <div class="grid plan">
        ${data.plan.map((d) => `
          <article class="card">
            <h3>Day ${d.day}: ${esc(d.focus)}</h3>
            <ul class="plain">${d.tasks.map((t, i) => {
              const id = `${d.day}-${i}`;
              return `<li><label><input type="checkbox" data-id="${id}" ${checks[id] ? "checked" : ""}> ${esc(t)}</label></li>`;
            }).join("")}</ul>
          </article>`).join("")}
      </div>
      <h2>Good starter tasks</h2>
      ${data.issues.length ? `<div class="grid">${data.issues.map((i) => `
        <article class="card">
          <h3>${i.url ? `<a href="${esc(i.url)}" target="_blank" rel="noopener noreferrer">${esc(i.title)}</a>` : esc(i.title)}</h3>
          ${i.detail ? `<p class="muted small">${esc(i.detail)}</p>` : ""}
          <div class="meta">${badge(i.source, i.source === "github" ? "good" : "muted")} ${i.labels.map((l) => badge(l, "muted")).join(" ")}</div>
        </article>`).join("")}</div>` : `<p class="muted">No starter tasks found.</p>`}`;
    root.querySelectorAll("input[type=checkbox]").forEach((c) => c.addEventListener("change", () => {
      checks[c.dataset.id] = c.checked;
      saveChecks(key, checks);
    }));
  });
}
