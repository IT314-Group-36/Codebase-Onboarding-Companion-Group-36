"""First-week task list: GitHub beginner issues + heuristic starter tasks + a day plan."""
import re

import httpx
from sqlalchemy import func, select

from ..config import settings
from ..models import FileRecord, Repository, Symbol
from ..schemas import DayPlan, OnboardingTasks, TaskItem
from .ingest import iter_source_files, read_repo_file
from pathlib import Path

_GH = re.compile(r"github\.com[/:]([^/]+)/([^/.]+)")
LABELS = ["good first issue", "good-first-issue", "help wanted"]


def fetch_github_issues(source: str, limit: int = 10) -> list[TaskItem]:
    m = _GH.search(source)
    if not m:
        return []
    owner, name = m.group(1), m.group(2)
    headers = {"Accept": "application/vnd.github+json"}
    if settings.github_token:
        headers["Authorization"] = f"Bearer {settings.github_token}"
    for label in LABELS:
        try:
            r = httpx.get(f"https://api.github.com/repos/{owner}/{name}/issues", headers=headers, timeout=10,
                          params={"labels": label, "state": "open", "per_page": limit})
            if r.status_code != 200:
                continue
            items = [i for i in r.json() if "pull_request" not in i]
        except Exception:
            continue
        if items:
            return [TaskItem(title=i["title"], detail=(i.get("body") or "")[:200] or None, source="github",
                             url=i["html_url"], labels=[l["name"] for l in i.get("labels", [])])
                    for i in items[:limit]]
    return []


def heuristic_tasks(db, repo: Repository, limit: int = 10) -> list[TaskItem]:
    tasks: list[TaskItem] = []
    # 1) TODO / FIXME comments
    if repo.local_path:
        root = Path(repo.local_path)
        for ap, rel in iter_source_files(root):
            if len(tasks) >= 5:
                break
            if rel.startswith(("tests/", "test/")):
                continue
            for n, line in enumerate(ap.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
                if re.search(r"\b(TODO|FIXME)\b", line):
                    tasks.append(TaskItem(title=f"Resolve TODO in {rel}:{n}", detail=line.strip()[:200],
                                          source="heuristic"))
                    break
    # 2) Undocumented functions
    rows = db.execute(
        select(Symbol.file_path, func.count()).where(
            Symbol.repo_id == repo.id, Symbol.kind.in_(["function", "method"]), Symbol.docstring.is_(None))
        .group_by(Symbol.file_path).order_by(func.count().desc()).limit(limit - len(tasks))).all()
    for path, n in rows:
        tasks.append(TaskItem(title=f"Add docstrings to {path}", source="heuristic",
                              detail=f"{n} function(s)/method(s) have no docstring — a safe first PR."))
    return tasks[:limit]


def build_plan(db, repo: Repository) -> list[DayPlan]:
    rows = db.execute(select(FileRecord.module, func.sum(FileRecord.line_count))
                      .where(FileRecord.repo_id == repo.id, FileRecord.language.notin_(
                          ["markdown", "json", "yaml", "toml", "other"]))
                      .group_by(FileRecord.module).order_by(func.sum(FileRecord.line_count).desc()).limit(3)).all()
    mods = [r[0] for r in rows] or ["the main module"]
    return [
        DayPlan(day=1, focus="Setup & orientation", tasks=[
            "Read the README and CONTRIBUTING docs", "Clone, install dependencies and run the project locally",
            "Open the module map (GET /map) and skim every module description"]),
        DayPlan(day=2, focus=f"Deep dive: {mods[0]}", tasks=[
            f"Read the key files in `{mods[0]}`", "Ask 3 questions about the code in the Q&A box",
            "Trace one request/feature end-to-end"]),
        DayPlan(day=3, focus=f"Connections: {', '.join(mods[1:]) or mods[0]}", tasks=[
            "Use the dependency graph to see how modules talk to each other",
            "Run the test suite and read 2 tests", "Use impact analysis on a function you find interesting"]),
        DayPlan(day=4, focus="First change", tasks=[
            "Pick a starter task from `issues`", "Make the change on a branch", "Run tests locally"]),
        DayPlan(day=5, focus="Ship it", tasks=[
            "Open your first pull request", "Address review comments", "Write down what confused you to improve the docs"]),
    ]


def onboarding_tasks(db, repo: Repository) -> OnboardingTasks:
    issues = fetch_github_issues(repo.source) if repo.source.startswith(("https://", "git@")) else []
    if not issues:
        issues = heuristic_tasks(db, repo)
    return OnboardingTasks(issues=issues, plan=build_plan(db, repo))
