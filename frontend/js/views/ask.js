import { badge, esc, fileLink, md, providerBadge, safe } from "../util.js";

const EXAMPLES = [
  "Where is the database logic handled?",
  "Which files handle HTTP routes?",
  "Where are the tests?",
  "How are repositories indexed?",
  "Where is authentication handled?",
];

function bubbleAnswer(r) {
  return `
    <div class="msg bot">
      <div>${md(r.answer)}</div>
      ${r.sources && r.sources.length ? `<div class="sources"><span class="muted small">Sources:</span>
        <ul class="plain">${r.sources.map((s) => `<li>${fileLink(s.path, s.line)} ${badge("score " + s.score, "muted")}
          <span class="muted small">${esc(s.reason)}</span></li>`).join("")}</ul></div>` : ""}
      ${r.used_ai === undefined ? "" : providerBadge(r.provider)}
    </div>`;
}

export async function mount(root, ctx) {
  root.innerHTML = `
    <h2>Ask about this codebase</h2>
    <div class="chips" id="examples">${EXAMPLES.map((q) => `<button class="chip" data-q="${esc(q)}">${esc(q)}</button>`).join("")}</div>
    <div id="chat" class="chat"></div>
    <form id="ask-form" class="ask-form">
      <input id="ask-input" placeholder="e.g. Where is the payment logic handled?" autocomplete="off" required minlength="3">
      <button class="btn primary" type="submit">Ask</button>
    </form>`;
  const chat = root.querySelector("#chat");
  const input = root.querySelector("#ask-input");

  async function ask(question) {
    chat.insertAdjacentHTML("beforeend", `<div class="msg user">${esc(question)}</div><div class="msg bot muted" id="thinking">Thinking…</div>`);
    chat.scrollTop = chat.scrollHeight;
    try {
      const r = await ctx.api.ask(ctx.repo.id, question);
      root.querySelector("#thinking")?.remove();
      chat.insertAdjacentHTML("beforeend", bubbleAnswer(r));
    } catch (e) {
      root.querySelector("#thinking")?.remove();
      chat.insertAdjacentHTML("beforeend", `<div class="msg bot error-box">${esc(e.message)}</div>`);
    }
    chat.scrollTop = chat.scrollHeight;
  }

  root.querySelector("#ask-form").addEventListener("submit", (e) => {
    e.preventDefault();
    const q = input.value.trim();
    if (q.length < 3) return;
    input.value = "";
    ask(q);
  });
  root.querySelector("#examples").addEventListener("click", (e) => {
    const b = e.target.closest("[data-q]");
    if (b) ask(b.dataset.q);
  });

  // Load earlier questions last (handlers above are already live). Insert before anything asked meanwhile.
  await safe(chat, async () => {
    const history = (await ctx.api.questions(ctx.repo.id, 10)).reverse();
    chat.insertAdjacentHTML("afterbegin", history.map((h) => `<div class="msg user">${esc(h.question)}</div>${bubbleAnswer({ answer: h.answer, sources: h.sources })}`).join(""));
    chat.scrollTop = chat.scrollHeight;
  });
}
