#!/usr/bin/env python3
"""Smoke test for Codebase Onboarding Companion. Needs only Python 3.9+ (no packages).

    python smoke_test.py                                   # defaults below
    python smoke_test.py --repo https://github.com/OWNER/REPO --base http://localhost:8000

Indexes a small public repo, waits for it, then checks every endpoint.
Exit code 0 = everything passed (an unset LLM_API_KEY only SKIPs the /ask check).
"""
import argparse
import json
import sys
import time
import urllib.error
import urllib.request

results = []


def call(base, method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base + path, data=data, method=method, headers={"content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw)
        except ValueError:
            return e.code, raw.decode(errors="replace")


def check(name, ok, detail=""):
    results.append(ok)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  ({detail})" if detail else ""))
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8000")
    ap.add_argument("--repo", default="https://github.com/pallets/itsdangerous")
    ap.add_argument("--timeout", type=int, default=900, help="seconds to wait for indexing")
    a = ap.parse_args()
    base = a.base.rstrip("/")

    print("1. API is up")
    try:
        code, body = call(base, "GET", "/health")
    except OSError as e:
        print(f"  [FAIL] cannot reach {base}: {e}\n  Is `docker compose up` running?")
        return 1
    if not check("GET /health", code == 200 and body == {"status": "ok"}, str(body)):
        return 1

    print(f"2. Register and index {a.repo}")
    code, repo = call(base, "POST", "/repos", {"url": a.repo})
    if not check("POST /repos accepted", code in (200, 202), f"HTTP {code}"):
        print("    ", repo)
        return 1
    rid, last, start = repo["id"], None, time.time()
    while time.time() - start < a.timeout:
        _, d = call(base, "GET", f"/repos/{rid}")
        state = (d["status"], d["stage"])
        if state != last:
            print(f"    status={d['status']} stage={d['stage']}")
            last = state
        if d["status"] in ("ready", "failed"):
            break
        time.sleep(2)
    if not check("indexing finished with status 'ready'", d["status"] == "ready", d.get("error") or ""):
        print("    Tip: `docker compose logs worker` shows the details.")
        return 1
    rep = d["index_report"] or {}
    check("commit SHA recorded", bool(d["commit_sha"]) and len(d["commit_sha"]) == 40)
    check("files, chunks and symbols found", rep.get("files", 0) > 0 and rep.get("chunks", 0) > 0 and rep.get("symbols", 0) > 0,
          f"files={rep.get('files')} chunks={rep.get('chunks')} symbols={rep.get('symbols')}")
    check("import graph built", rep.get("import_edges", 0) > 0, f"import_edges={rep.get('import_edges')} call_edges={rep.get('call_edges')}")
    for w in d["warnings"]:
        print(f"    note: {w}")

    print("3. Read endpoints")
    code, m = call(base, "GET", f"/repos/{rid}/map")
    check("GET /map has modules", code == 200 and len(m["modules"]) > 0, f"{len(m.get('modules', []))} modules")
    code, files = call(base, "GET", f"/repos/{rid}/files")
    check("GET /files lists files", code == 200 and len(files) > 0, f"{len(files)} files")
    sym = None
    code_langs = {"python", "javascript", "typescript", "tsx"}
    for f in (f for f in files if (f["language"] or "").lower() in code_langs and not f["sensitive"]):
        code, fd = call(base, "GET", f"/repos/{rid}/files/{f['path']}")
        if code == 200 and fd["symbols"]:
            sym = fd["symbols"][0]
            check("GET /files/{path} returns symbols", True, f"{f['path']}: {len(fd['symbols'])} symbols")
            break
    if not check("found a parsed file with symbols to test against", sym is not None,
                 "" if sym else "this repo has no Python/JS/TS code; try another --repo"):
        return 1

    print("4. Search, symbols, impact")
    code, hits = call(base, "POST", f"/repos/{rid}/search", {"query": "where is the main logic handled?", "k": 3})
    check("POST /search returns hits", code == 200 and len(hits["hits"]) > 0)
    code, s = call(base, "GET", f"/repos/{rid}/symbols?q={sym['name']}")
    check("GET /symbols finds a known symbol", code == 200 and any(x["uid"] == sym["uid"] for x in s), sym["uid"])
    from urllib.parse import quote
    code, imp = call(base, "GET", f"/repos/{rid}/impact?symbol={quote(sym['uid'])}&depth=3")
    check("GET /impact works", code == 200 and "affected_symbols" in imp,
          f"{len(imp.get('affected_symbols', []))} symbols, {len(imp.get('affected_files', []))} files likely affected")

    print("5. Ask (needs LLM_API_KEY)")
    code, ans = call(base, "POST", f"/repos/{rid}/ask", {"question": "What does this project do?"})
    if code == 503:
        print("  [SKIP] /ask returned 503: no LLM_API_KEY configured (expected without a key)")
    else:
        text = ans.get("answer") if isinstance(ans, dict) else None
        detail = text or (ans.get("detail") if isinstance(ans, dict) else str(ans))
        check("POST /ask returns an answer", code == 200 and bool(text), f"HTTP {code}: {str(detail)[:90]}")

    print("6. First-week task list (GitHub issues)")
    # The worker syncs issues right after indexing. If that has not happened, start it ourselves (this also tests POST).
    code, st = call(base, "GET", f"/repos/{rid}/issues/sync")
    if code == 200 and st["status"] == "never":
        call(base, "POST", f"/repos/{rid}/issues/sync")
    deadline = time.time() + 180
    while time.time() < deadline:
        code, st = call(base, "GET", f"/repos/{rid}/issues/sync")
        if code != 200 or st["status"] in ("ok", "failed"):
            break
        time.sleep(2)
    synced = code == 200 and st["status"] == "ok"
    check("issue sync finished with status 'ok'", synced,
          f"fetched={st.get('fetched')} {st.get('message') or ''}" if code == 200 else f"HTTP {code}")
    if not synced and code == 200 and "rate limit" in (st.get("message") or "").lower():
        print("    Tip: put GITHUB_TOKEN=<your token> in .env and run `docker compose up -d --build` again.")

    code, plan = call(base, "GET", f"/repos/{rid}/onboarding-tasks")
    tasks = plan["tasks"] if code == 200 and isinstance(plan, dict) else []
    if check("GET /onboarding-tasks returns a plan", code == 200 and len(tasks) > 0, f"HTTP {code}, {len(tasks)} tasks"):
        safe_paths = {f["path"] for f in files if not f["sensitive"]}
        days = [t["suggested_day"] for t in tasks]
        check("days are 1-5 and in order, difficulty is easy/medium",
              all(1 <= d <= 5 for d in days) and days == sorted(days) and all(t["difficulty"] in ("easy", "medium") for t in tasks))
        check("related files exist in the repo (never sensitive ones)",
              all(f["path"] in safe_paths for t in tasks for f in t["related_files"]))
        issue_tasks = [t for t in tasks if t["source"] == "issue"]
        check("issue tasks link to GitHub issues",
              all((t["url"] or "").startswith("https://github.com/") and t["number"] for t in issue_tasks),
              f"{len(issue_tasks)} issue task(s)")
        print(f"    {len(issue_tasks)} issue task(s), {len(tasks) - len(issue_tasks)} orientation task(s), "
              f"fallback_used={plan['fallback_used']}, eligible_issues={plan['eligible_issues']}")
        for t in tasks:
            print(f"    day {t['suggested_day']}: [{t['source']}/{t['difficulty']}] {t['title'][:70]}")
        for n in plan["notes"]:
            print(f"    note: {n}")
    code, ex = call(base, "GET", f"/repos/{rid}/onboarding-tasks?explain=true")
    if code == 503:
        print("  [SKIP] explain=true returned 503: no LLM_API_KEY configured (expected without a key)")
    else:
        guided = [t for t in ex["tasks"] if t["guide"]] if code == 200 and isinstance(ex, dict) else []
        has_issues = any(t["source"] == "issue" for t in ex["tasks"]) if code == 200 and isinstance(ex, dict) else False
        check("explain=true adds guides to issue tasks", code == 200 and (bool(guided) or not has_issues), f"HTTP {code}, {len(guided)} guides")

    print(f"\n{sum(results)}/{len(results)} checks passed")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
