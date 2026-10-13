import { colorFor, esc, safe } from "../util.js";

const W = 960, H = 620;

/** Small deterministic force-directed layout (Fruchterman-Reingold). */
export function layout(nodes, edges) {
  const n = nodes.length;
  const idx = new Map(nodes.map((nd, i) => [nd.id, i]));
  const pos = nodes.map((_, i) => ({
    x: W / 2 + Math.cos((2 * Math.PI * i) / Math.max(n, 1)) * W * 0.32,
    y: H / 2 + Math.sin((2 * Math.PI * i) / Math.max(n, 1)) * H * 0.32,
  }));
  if (n < 2) return pos;
  const k = Math.sqrt((W * H) / n) * 0.55;
  let temp = W / 10;
  for (let it = 0; it < 250; it++) {
    const disp = pos.map(() => ({ x: 0, y: 0 }));
    for (let i = 0; i < n; i++) {
      for (let j = i + 1; j < n; j++) {
        let dx = pos[i].x - pos[j].x, dy = pos[i].y - pos[j].y;
        const d = Math.max(Math.hypot(dx, dy), 0.01);
        const f = (k * k) / d;
        dx /= d; dy /= d;
        disp[i].x += dx * f; disp[i].y += dy * f;
        disp[j].x -= dx * f; disp[j].y -= dy * f;
      }
    }
    for (const e of edges) {
      const a = idx.get(e.source), b = idx.get(e.target);
      if (a === undefined || b === undefined) continue;
      let dx = pos[a].x - pos[b].x, dy = pos[a].y - pos[b].y;
      const d = Math.max(Math.hypot(dx, dy), 0.01);
      const f = (d * d) / k;
      dx /= d; dy /= d;
      disp[a].x -= dx * f; disp[a].y -= dy * f;
      disp[b].x += dx * f; disp[b].y += dy * f;
    }
    for (let i = 0; i < n; i++) {
      const d = Math.max(Math.hypot(disp[i].x, disp[i].y), 0.01);
      const m = Math.min(d, temp);
      pos[i].x = Math.min(W - 60, Math.max(60, pos[i].x + (disp[i].x / d) * m));
      pos[i].y = Math.min(H - 30, Math.max(30, pos[i].y + (disp[i].y / d) * m));
    }
    temp *= 0.97;
  }
  return pos;
}

function draw(container, graph, ctx) {
  const { nodes, edges, level } = graph;
  if (!nodes.length || !edges.length) {
    container.innerHTML = `<p class="muted">No internal dependencies were found for this view.</p>`;
    return;
  }
  const pos = layout(nodes, edges);
  const idx = new Map(nodes.map((nd, i) => [nd.id, i]));
  const maxW = Math.max(...edges.map((e) => e.weight));
  const lines = edges.map((e) => {
    const a = pos[idx.get(e.source)], b = pos[idx.get(e.target)];
    if (!a || !b) return "";
    return `<line data-s="${esc(e.source)}" data-t="${esc(e.target)}" x1="${a.x}" y1="${a.y}" x2="${b.x}" y2="${b.y}"
      stroke-width="${1 + (3 * e.weight) / maxW}" marker-end="url(#arrow)"><title>${esc(e.source)} → ${esc(e.target)}${level === "module" ? " (" + e.weight + " imports)" : ""}</title></line>`;
  }).join("");
  const circles = nodes.map((nd, i) => `
    <g class="gnode" data-id="${esc(nd.id)}" data-level="${level}" transform="translate(${pos[i].x},${pos[i].y})">
      <circle r="${level === "module" ? 11 : 7}" fill="${colorFor(level === "module" ? nd.id : nd.module)}"></circle>
      <text y="${level === "module" ? -16 : -11}" text-anchor="middle">${esc(nd.label)}</text>
      <title>${esc(nd.id)}</title>
    </g>`).join("");
  container.innerHTML = `
    <svg viewBox="0 0 ${W} ${H}" class="graph-svg" role="img" aria-label="Dependency graph">
      <defs><marker id="arrow" viewBox="0 0 10 10" refX="18" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
        <path d="M 0 0 L 10 5 L 0 10 z" class="arrowhead"></path></marker></defs>
      <g class="edges">${lines}</g>${circles}
    </svg>
    <p class="muted small">${nodes.length} nodes · ${edges.length} edges · arrows point from importer to imported. Click a node to open it.</p>`;
  container.querySelectorAll(".gnode").forEach((g) => {
    g.addEventListener("click", () => (g.dataset.level === "module" ? ctx.openModule(g.dataset.id) : ctx.openFile(g.dataset.id)));
    g.addEventListener("mouseenter", () => container.querySelectorAll("line").forEach((l) =>
      l.classList.toggle("hot", l.dataset.s === g.dataset.id || l.dataset.t === g.dataset.id)));
    g.addEventListener("mouseleave", () => container.querySelectorAll("line.hot").forEach((l) => l.classList.remove("hot")));
  });
}

export async function mount(root, ctx) {
  root.innerHTML = `
    <h2>Dependency graph</h2>
    <div class="meta">
      <label><input type="radio" name="lvl" value="module" checked> Module level</label>
      <label><input type="radio" name="lvl" value="file"> File level</label>
    </div>
    <div id="graph-box"><p class="muted">Loading…</p></div>`;
  const box = root.querySelector("#graph-box");
  async function load(level) {
    box.innerHTML = `<p class="muted">Loading…</p>`;
    await safe(box, async () => draw(box, await ctx.api.graph(ctx.repo.id, level, level === "file" ? 120 : 300), ctx));
  }
  root.querySelectorAll("input[name=lvl]").forEach((r) => r.addEventListener("change", () => load(r.value)));
  await load("module");
}
