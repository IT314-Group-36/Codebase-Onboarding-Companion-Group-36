import { esc, fileLink, safe } from "../util.js";

export async function mount(root, ctx) {
  root.innerHTML = `<p class="muted">Loading module map…</p>`;
  await safe(root, async () => {
    const { repo, modules } = await ctx.api.map(ctx.repo.id);
    const totalLines = modules.reduce((n, m) => n + m.line_count, 0);
    root.innerHTML = `
      <div class="stats">
        <div class="stat"><b>${repo.file_count}</b><span>files</span></div>
        <div class="stat"><b>${modules.length}</b><span>modules</span></div>
        <div class="stat"><b>${totalLines.toLocaleString()}</b><span>lines</span></div>
      </div>
      <h2>Module map</h2>
      <p class="muted">Each module with what it is responsible for. Click a file to read an explanation.</p>
      <div class="grid">
        ${modules.map((m) => `
          <article class="card">
            <h3>${esc(m.name)}</h3>
            <p>${esc(m.description)}</p>
            <p class="muted small">${m.file_count} files · ${m.line_count.toLocaleString()} lines
              ${m.languages.length ? "· " + esc(m.languages.join(", ")) : ""}</p>
            <ul class="plain">
              ${m.key_files.map((f) => `<li>${fileLink(f.path)}<div class="muted small">${esc(f.summary || "")}</div></li>`).join("")}
            </ul>
            <button class="btn small" data-module="${esc(m.name)}">Browse all files →</button>
          </article>`).join("")}
      </div>`;
    root.querySelectorAll("[data-module]").forEach((b) =>
      b.addEventListener("click", () => ctx.openModule(b.dataset.module)));
  });
}
