import { badge, debounce, esc, fileLink, md, providerBadge, safe } from "../util.js";

export async function mount(root, ctx) {
  root.innerHTML = `
    <div class="split">
      <aside class="pane list-pane">
        <input id="f-search" placeholder="Filter files by path…" />
        <select id="f-module"><option value="">All modules</option></select>
        <div id="f-count" class="muted small"></div>
        <ul id="f-list" class="file-list"></ul>
      </aside>
      <section class="pane detail-pane" id="f-detail">
        <p class="muted">Select a file to see its explanation, symbols, dependencies and source.</p>
      </section>
    </div>`;

  const search = root.querySelector("#f-search");
  const moduleSel = root.querySelector("#f-module");
  const list = root.querySelector("#f-list");
  const detail = root.querySelector("#f-detail");
  const count = root.querySelector("#f-count");
  let selected = null;

  const pending = ctx.takePending("file");
  const pendingModule = ctx.takePending("module");

  list.addEventListener("click", (e) => {
    const li = e.target.closest("li[data-path]");
    if (li) openFile(li.dataset.path);
  });
  search.addEventListener("input", debounce(() => safe(list, loadList)));
  moduleSel.addEventListener("change", () => safe(list, loadList));

  await safe(root, async () => {
    const { modules } = await ctx.api.map(ctx.repo.id);
    moduleSel.innerHTML += modules.map((m) => `<option value="${esc(m.name)}">${esc(m.name)}</option>`).join("");
    if (pendingModule) moduleSel.value = pendingModule;
  });

  async function loadList() {
    const files = await ctx.api.files(ctx.repo.id, { q: search.value.trim(), module: moduleSel.value, limit: 300 });
    count.textContent = files.length >= 300 ? "Showing first 300 — refine the filter" : `${files.length} file(s)`;
    list.innerHTML = files.map((f) => `
      <li data-path="${esc(f.path)}" class="${f.path === selected ? "selected" : ""}">
        <div class="file-name">${esc(f.path.split("/").pop())}</div>
        <div class="muted small">${esc(f.path)}</div>
      </li>`).join("") || `<li class="muted">No files match.</li>`;
  }

  async function openFile(path, line) {
    selected = path;
    list.querySelectorAll("li").forEach((li) => li.classList.toggle("selected", li.dataset.path === path));
    detail.innerHTML = `<p class="muted">Loading ${esc(path)}…</p>`;
    await safe(detail, async () => {
      const [info, src] = await Promise.all([
        ctx.api.file(ctx.repo.id, path),
        ctx.api.source(ctx.repo.id, path).catch(() => null),
      ]);
      detail.innerHTML = `
        <h2 class="mono">${esc(info.path)}</h2>
        <div class="meta">
          ${badge(info.language)} ${badge(info.module)} ${badge(info.line_count + " lines")}
          ${info.used_ai ? providerBadge(info.provider) : badge("built-in summary", "muted")}
          <button class="btn small" id="to-impact">💥 Impact analysis</button>
        </div>
        <div class="explain">${md(info.explanation)}</div>

        <h3>Symbols (${info.symbols.length})</h3>
        ${info.symbols.length ? `<table class="tbl"><thead><tr><th>Name</th><th>Kind</th><th>Line</th><th>Signature</th></tr></thead><tbody>
          ${info.symbols.map((s) => `<tr data-line="${s.line}" class="sym-row"><td class="mono">${esc(s.name)}</td>
            <td>${esc(s.kind)}</td><td>${s.line}</td><td class="mono small">${esc(s.signature || "")}</td></tr>`).join("")}
          </tbody></table>` : `<p class="muted">No top-level symbols detected.</p>`}

        <div class="cols">
          <div><h3>Imports (${info.imports.length})</h3>
            <ul class="plain">${info.imports.map((p) => `<li>${fileLink(p)}</li>`).join("") || `<li class="muted">None inside this repo</li>`}</ul>
            ${info.external_imports.length ? `<div class="chips">${info.external_imports.slice(0, 20).map((e) => badge(e, "muted")).join(" ")}</div>` : ""}
          </div>
          <div><h3>Imported by (${info.imported_by.length})</h3>
            <ul class="plain">${info.imported_by.map((p) => `<li>${fileLink(p)}</li>`).join("") || `<li class="muted">Nothing imports this file</li>`}</ul>
          </div>
        </div>

        <h3>Source ${src && src.truncated ? `<span class="muted small">(first 3000 lines)</span>` : ""}</h3>
        <pre class="code" id="code">${src ? src.content.split("\n").slice(0, 3000).map((l, i) =>
          `<div class="ln" id="L${i + 1}"><span class="no">${i + 1}</span><span class="tx">${esc(l) || " "}</span></div>`).join("") : "Source not available."}</pre>`;

      detail.querySelector("#to-impact").addEventListener("click", () => ctx.openImpact(path));
      detail.querySelectorAll(".sym-row").forEach((r) => r.addEventListener("click", () => highlight(r.dataset.line)));
      if (line) highlight(line);
    });
  }

  function highlight(line) {
    detail.querySelectorAll(".ln.hl").forEach((e) => e.classList.remove("hl"));
    const el = detail.querySelector(`#L${CSS.escape(String(line))}`);
    if (el) {
      el.classList.add("hl");
      el.scrollIntoView({ block: "center" });
    }
  }

  await safe(list, loadList);
  if (pending) openFile(pending.path, pending.line);
}
