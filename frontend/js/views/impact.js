import { badge, esc, fileLink, safe } from "../util.js";

const list = (items) => items.length
  ? `<ul class="plain">${items.map((p) => `<li>${fileLink(p)}</li>`).join("")}</ul>`
  : `<p class="muted">None</p>`;

export async function mount(root, ctx) {
  root.innerHTML = `
    <h2>What would break if I change this?</h2>
    <p class="muted">Enter a file path or a function/class name. Uses the import graph plus a symbol-usage scan.</p>
    <form id="imp-form" class="ask-form">
      <input id="imp-input" list="imp-options" placeholder="backend/app/models.py  or  index_repository" required>
      <datalist id="imp-options"></datalist>
      <button class="btn primary" type="submit">Analyze</button>
    </form>
    <div id="imp-result"></div>`;
  const input = root.querySelector("#imp-input");
  const out = root.querySelector("#imp-result");

  // Suggestions: file paths + symbol names
  ctx.api.files(ctx.repo.id, { limit: 300 }).then((files) => {
    ctx.api.symbols(ctx.repo.id, { limit: 100 }).then((syms) => {
      root.querySelector("#imp-options").innerHTML =
        [...files.map((f) => f.path), ...new Set(syms.map((s) => s.name))].map((v) => `<option value="${esc(v)}">`).join("");
    }).catch(() => {});
  }).catch(() => {});

  async function run(target) {
    input.value = target;
    out.innerHTML = `<p class="muted">Analyzing…</p>`;
    await safe(out, async () => {
      const r = await ctx.api.impact(ctx.repo.id, target);
      const riskKind = { none: "muted", low: "good", medium: "warn", high: "bad" }[r.risk];
      out.innerHTML = r.kind === "unknown"
        ? `<div class="error-box">${esc(r.notes)}</div>`
        : `<div class="card">
            <div class="meta">${badge(r.kind)} <span class="mono">${esc(r.target)}</span> ${badge("risk: " + r.risk, riskKind)}</div>
            <p>${esc(r.notes)}</p>
            <h3>Defined in</h3>${list(r.defined_in)}
            <div class="cols">
              <div><h3>Directly affected (${r.directly_affected.length})</h3>${list(r.directly_affected)}</div>
              <div><h3>Transitively affected (${r.transitively_affected.length})</h3>${list(r.transitively_affected)}</div>
            </div>
            <h3>Tests to run (${r.affected_tests.length})</h3>${list(r.affected_tests)}
          </div>`;
    });
  }

  root.querySelector("#imp-form").addEventListener("submit", (e) => {
    e.preventDefault();
    run(input.value.trim());
  });

  const pending = ctx.takePending("impact");
  if (pending) run(pending);
}
