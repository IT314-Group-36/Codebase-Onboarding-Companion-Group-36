"""The AI engine: turns code context into plain-English explanations and answers.

Two providers:
  * "gemini":    real LLM (Google Gemini), used when GEMINI_API_KEY is set
  * "offline":   deterministic heuristics (no network), always available as fallback
"""
import logging
import re

import httpx

from .config import settings

log = logging.getLogger("engine")

SYSTEM_EXPLAIN = (
    "You are a senior engineer onboarding a new teammate. Explain the given source file in plain English "
    "in 4-7 short sentences: its purpose, its key functions/classes, what it depends on, and where a newcomer "
    "should start reading. Do not invent things that are not in the code. Use `backticks` for identifiers."
)
SYSTEM_ANSWER = (
    "You help a new developer navigate an unfamiliar codebase. Answer using ONLY the provided context "
    "(file paths, summaries and symbols). Name the specific files (in `backticks`) and say why. "
    "If the context is not enough, say so. Keep it under 150 words."
)


# ---------------------------------------------------------------- LLM
def _llm(system: str, user: str) -> str | None:
    if not settings.gemini_api_key:
        return None
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{settings.gemini_model}:generateContent"
    try:
        r = httpx.post(
            url,
            headers={"x-goog-api-key": settings.gemini_api_key, "content-type": "application/json"},
            json={
                "systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": user}]}],
                # Gemini 2.5/3.x "thinking" tokens count toward this limit, so keep it generous.
                "generationConfig": {"maxOutputTokens": 2048, "temperature": 0.3},
            },
            timeout=settings.llm_timeout,
        )
        r.raise_for_status()
        candidates = r.json().get("candidates") or []
        if not candidates:  # e.g. blocked by safety filters
            return None
        parts = (candidates[0].get("content") or {}).get("parts") or []
        text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
        return text.strip() or None
    except Exception as exc:
        log.warning("LLM call failed, falling back to offline engine: %s", exc)
        return None


# ---------------------------------------------------------------- offline helpers
_VERBS = {"get": "Gets", "set": "Sets", "create": "Creates", "delete": "Deletes", "update": "Updates",
          "list": "Lists", "read": "Reads", "write": "Writes", "load": "Loads", "save": "Saves",
          "parse": "Parses", "build": "Builds", "check": "Checks", "validate": "Validates",
          "handle": "Handles", "run": "Runs", "init": "Initialises", "fetch": "Fetches", "send": "Sends",
          "add": "Adds", "remove": "Removes", "find": "Finds", "search": "Searches", "resolve": "Resolves",
          "analyze": "Analyzes", "analyse": "Analyses", "render": "Renders", "mount": "Mounts",
          "is": "Checks whether", "has": "Checks whether it has", "to": "Converts to", "make": "Makes",
          "index": "Indexes", "explain": "Explains", "ask": "Handles asking", "purge": "Purges"}

_ROLES = [
    (r"(^|/)(tests?|__tests__)(/|$)|(^|/)test_|_test\.|\.test\.|\.spec\.", "that contains automated tests"),
    (r"(^|/)(routers?|routes?|controllers?|endpoints?|api)(/|\.)", "that defines HTTP endpoints"),
    (r"(^|/)schemas?(/|\.)", "that defines request/response data shapes"),
    (r"(^|/)models?(/|\.)", "that defines data models (the database layer)"),
    (r"(^|/)(services?|usecases?)(/|\.)", "that holds business logic"),
    (r"(^|/)(config|settings)", "that holds configuration"),
    (r"(^|/)(database|db)(/|\.)", "that sets up database access"),
    (r"(^|/)(utils?|helpers?)(/|\.)", "with shared helper functions"),
    (r"(^|/)(views?|pages?|components?)(/|\.)", "that builds part of the user interface"),
    (r"(^|/)(main|app|index|server|run)\.", "that acts as an entry point"),
    (r"\.css$", "that styles the interface"),
    (r"\.html$", "that provides page markup"),
    (r"\.md$", "that documents the project"),
]


def humanize(name: str) -> str:
    base = name.split(".")[-1]
    words = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", base).replace("_", " ").strip().lower().split()
    if not words:
        return name
    verb = _VERBS.get(words[0])
    if verb and len(words) > 1:
        return f"{verb} {' '.join(words[1:])}"
    if verb:
        return verb
    return "Handles " + " ".join(words)


def _leading_description(code: str) -> str | None:
    m = re.match(r'\s*(?:#!.*\n)?\s*(?:"""|\'\'\')(.+?)(?:"""|\'\'\')', code, re.S)
    if m:
        return " ".join(m.group(1).strip().split("\n\n")[0].split())[:240]
    lines = []
    for line in code.splitlines()[:12]:
        t = line.strip()
        if t.startswith(("//", "#")) and not t.startswith("#!"):
            lines.append(t.lstrip("/# ").strip())
        elif t.startswith(("/*", "*")):
            lines.append(t.strip("/* ").strip())
        elif t == "" and not lines:
            continue
        else:
            break
    text = " ".join(l for l in lines if l)
    return text[:240] or None


def _imports(code: str) -> list[str]:
    found = re.findall(r"^\s*(?:from\s+([\w\.]+)\s+import|import\s+([\w\.]+)|import\s+.*?from\s+['\"]([^'\"]+)['\"])",
                       code, re.M)
    names = [a or b or c for a, b, c in found]
    return list(dict.fromkeys(n for n in names if n))


def explain_offline(path: str, language: str, code: str, symbols: list[dict]) -> str:
    role = next((r for pat, r in _ROLES if re.search(pat, path.lower())), "")
    article = "an" if language[:1] in "aeiou" else "a"
    parts = [f"`{path}` is {article} {language} file {role}.".replace(" .", ".")]
    lead = _leading_description(code)
    if lead:
        parts.append(lead if lead.endswith(".") else lead + ".")

    classes = [s for s in symbols if s.get("kind") == "class"]
    funcs = [s for s in symbols if s.get("kind") in ("function", "method")]
    if classes or funcs:
        bits = []
        if classes:
            bits.append(f"{len(classes)} class(es) ({', '.join('`'+c['name']+'`' for c in classes[:3])})")
        if funcs:
            bits.append(f"{len(funcs)} function(s)/method(s)")
        parts.append("It defines " + " and ".join(bits) + ".")
        shown = [s for s in symbols if s.get("kind") != "method"][:5] or symbols[:5]
        parts.append("Main pieces:\n" + "\n".join(f"• `{s['name']}`: {humanize(s['name'])}" for s in shown))
    elif code.strip():
        parts.append(f"It has {len(code.splitlines())} lines and defines no top-level functions or classes.")

    imps = _imports(code)
    if imps:
        parts.append(f"It pulls in {len(imps)} module(s), e.g. " + ", ".join(f"`{i}`" for i in imps[:4]) + ".")
    if symbols:
        parts.append(f"Start reading at `{symbols[0]['name']}`.")
    return "\n".join(parts)


def answer_offline(question: str, contexts: list[dict]) -> str:
    if not contexts:
        return "I could not find relevant code for that question in the index."
    top = contexts[0]
    out = [f"The code behind this most likely lives in `{top['path']}`."]
    if top.get("summary"):
        s = top["summary"]
        out.append(s if s.endswith(".") else s + ".")
    syms = top.get("symbols") or []
    if syms:
        out.append("Look at: " + ", ".join(f"`{s}`" for s in syms[:3]) + ".")
    related = contexts[1:4]
    if related:
        out.append("Also related:\n" + "\n".join(
            f"• `{c['path']}`" + (f" ({c['reason']})" if c.get("reason") else "") for c in related))
    out.append("Open the file explanation to see what it imports and who depends on it before changing it.")
    return "\n".join(out)


# ---------------------------------------------------------------- public API
def explain_file(inp: dict) -> tuple[str, str]:
    path, lang = inp.get("path", "?"), inp.get("language", "text")
    code, symbols = inp.get("code", ""), inp.get("symbols", [])
    sym_txt = "\n".join(f"- {s.get('signature') or s.get('name')}" for s in symbols[:25])
    out = _llm(SYSTEM_EXPLAIN, f"File: {path} ({lang})\nSymbols:\n{sym_txt}\n\nSource:\n{code[:8000]}")
    return (out, "gemini") if out else (explain_offline(path, lang, code, symbols), "offline")


def answer_question(inp: dict) -> tuple[str, str]:
    q, ctxs = inp.get("question", ""), inp.get("contexts", [])
    ctx_txt = "\n\n".join(f"File: {c.get('path')}\nSummary: {c.get('summary')}\nMatched: {c.get('reason')}\n"
                          f"Symbols: {', '.join(c.get('symbols') or [])}" for c in ctxs[:6])
    out = _llm(SYSTEM_ANSWER, f"Question: {q}\n\nContext:\n{ctx_txt}")
    return (out, "gemini") if out else (answer_offline(q, ctxs), "offline")
