"""First-week task list: which issues suit a newcomer, in what order, and where in the code to start.

Everything here is a pure function (no DB, no network, no LLM), so the rules are easy to read, test and defend.

Ranking in one paragraph: an issue is only considered if a maintainer marked it as approachable (a beginner, easy,
"help wanted" or docs label), nobody is assigned, it is not locked/closed-out (wontfix, duplicate, ...) and it is not
marked hard. Eligible issues get a score from the label strength, how clear the description is, how much discussion
there is, and how recently it was touched. The best `limit` issues are then ordered easy -> harder so the week builds up.
"""
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

# ---- label vocabulary --------------------------------------------------------------------------------------------

_NORMALISE = re.compile(r"[\s_\-]+")


def norm_label(name: str) -> str:
    """'Good-First_Issue' -> 'good first issue' (labels are written many ways across projects)."""
    return _NORMALISE.sub(" ", name.lower()).strip()


# (family, weight, pattern). A label can match several; the strongest weight counts.
_POSITIVE = [
    ("beginner", 40, re.compile(r"good first (issue|bug|contribution)|first timers?( only)?|first contribution|"
                                r"\bbeginners?\b|\bnewcomers?\b|starter task")),
    ("easy", 30, re.compile(r"\beasy\b|low hanging fruit|\btrivial\b")),
    ("help wanted", 15, re.compile(r"help wanted")),
    ("docs", 10, re.compile(r"\bdocs?\b|documentation|\btypo\b")),
]
_HARD = re.compile(r"\b(hard|difficult|complex|advanced|expert|epic)\b|breaking change|needs design|\brfc\b")
_EXCLUDED = re.compile(r"won'?t ?fix|\bduplicate\b|\binvalid\b|\bblocked\b|on hold|\bstale\b|\bquestion\b|\bdiscussion\b")

DIFFICULTY_RANK = {"easy": 0, "medium": 1}
WEEK_DAYS = 5
MIN_TASKS = 3            # below this many issue tasks, orientation tasks are added so the week is never empty


@dataclass(frozen=True)
class IssueInfo:
    number: int
    title: str
    body: str
    labels: list[str]
    url: str
    comments: int = 0
    assignees: int = 0
    locked: bool = False
    updated_at: datetime | None = None


@dataclass
class ScoredIssue:
    info: IssueInfo
    score: float
    difficulty: str
    reasons: list[str] = field(default_factory=list)


def label_families(labels: list[str]) -> dict[str, int]:
    """{'beginner': 40, 'help wanted': 15, ...} for the labels that matter to a newcomer."""
    out: dict[str, int] = {}
    for lab in labels:
        n = norm_label(lab)
        for family, weight, rx in _POSITIVE:
            if rx.search(n):
                out[family] = max(out.get(family, 0), weight)
    return out


def ineligible_reason(info: IssueInfo) -> str | None:
    """Why this issue must not be offered to a newcomer, or None when it can be."""
    normed = [norm_label(x) for x in info.labels]
    if info.locked:
        return "locked"
    if info.assignees > 0:
        return "already assigned"
    if any(_EXCLUDED.search(n) for n in normed):
        return "marked wontfix/duplicate/invalid/blocked/question"
    if any(_HARD.search(n) for n in normed):
        return "marked as hard"
    if not label_families(info.labels):
        return "no beginner-friendly label"
    return None


def _days_since(moment: datetime | None, now: datetime) -> int | None:
    if moment is None:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return max((now - moment).days, 0)


def score_issue(info: IssueInfo, now: datetime) -> ScoredIssue:
    """Score an ELIGIBLE issue (call ineligible_reason first). Higher is a better first task."""
    families = label_families(info.labels)
    score = float(max(families.values()))
    reasons = [f"Labelled '{next(lab for lab in info.labels if _label_is(lab, families))}'"]
    if len(families) > 1 and "help wanted" in families:
        score += 10
        reasons.append("Maintainers also marked it 'help wanted'")

    body_len = len(info.body.strip())
    if body_len == 0:
        score -= 15
        reasons.append("No description yet, so you would have to ask what is wanted")
    elif 80 <= body_len <= 3000:
        score += 10
        reasons.append("Clear description")
    elif body_len > 3000:
        score -= 5
        reasons.append("Long description, read it carefully first")

    if info.comments == 0:
        pass
    elif info.comments <= 5:
        score += 5
        reasons.append("A few comments add context")
    elif info.comments > 15:
        score -= 15
        reasons.append("Long discussion thread, the scope may be unclear")

    age = _days_since(info.updated_at, now)
    if age is not None:
        if age <= 90:
            score += 10
            reasons.append("Updated recently")
        elif age <= 365:
            score += 5
        elif age > 730:
            score -= 10
            reasons.append("Not touched for over two years, check it is still wanted")

    gentle = bool(families.keys() & {"beginner", "easy", "docs"})
    difficulty = "easy" if gentle and info.comments <= 5 and body_len <= 2500 else "medium"
    return ScoredIssue(info=info, score=score, difficulty=difficulty, reasons=reasons)


def _label_is(label: str, families: dict[str, int]) -> bool:
    """True when this label is the one that gave the issue its strongest family weight."""
    best = max(families.values())
    n = norm_label(label)
    return any(rx.search(n) and w == best for _fam, w, rx in _POSITIVE)


def rank_issues(issues: list[IssueInfo], now: datetime, limit: int = 5) -> tuple[list[ScoredIssue], int]:
    """Returns (the week's issues ordered easy -> harder, how many issues were eligible at all)."""
    scored = [score_issue(i, now) for i in issues if ineligible_reason(i) is None]
    best = sorted(scored, key=lambda s: (-s.score, s.info.number))[:limit]
    week = sorted(best, key=lambda s: (DIFFICULTY_RANK[s.difficulty], -s.score, s.info.number))
    return week, len(scored)


def assign_days(count: int) -> list[int]:
    """Spread `count` tasks over a five-day week: 5 tasks -> 1..5, 3 tasks -> 1, 2, 4, 1 task -> day 1."""
    return [1 + (i * WEEK_DAYS) // count for i in range(count)] if count else []


# ---- text helpers ------------------------------------------------------------------------------------------------

_HTML_COMMENT = re.compile(r"<!--.*?-->", re.S)
_CODE_FENCE = re.compile(r"```.*?```", re.S)
_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_TAG = re.compile(r"<[^>]+>")
_MD_NOISE = re.compile(r"[#>*_`~|]+")


def plain_summary(body: str, limit: int = 240) -> str:
    """The start of an issue body as one tidy plain-text line (issue templates, images and code fences removed)."""
    text = _HTML_COMMENT.sub(" ", body or "")
    text = _CODE_FENCE.sub(" ", text)
    text = _IMAGE.sub(" ", text)
    text = _LINK.sub(r"\1", text)
    text = _TAG.sub(" ", text)
    text = " ".join(_MD_NOISE.sub(" ", text).split())
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0].rstrip(".,;:!-")
    return cut + "…"


_PATH_TOKEN = re.compile(r"[\w./\-]+\.[A-Za-z0-9]{1,8}")


class PathIndex:
    """Finds repo files an issue mentions. Exact path first, then an unambiguous path suffix, then a unique file name."""

    def __init__(self, paths: list[str]):
        self.paths = set(paths)
        self._by_name: dict[str, list[str]] = {}
        for p in paths:
            self._by_name.setdefault(p.rsplit("/", 1)[-1], []).append(p)

    def _resolve(self, token: str) -> str | None:
        token = token.rstrip(".,:;)(\"'`[]").lstrip(",:;)(\"'`[]")
        while token.startswith("./"):                      # './src/a.py' -> 'src/a.py', but '.github/x.yml' stays intact
            token = token[2:]
        token = token.lstrip("/")
        if not token:
            return None
        if token in self.paths:
            return token
        name = token.rsplit("/", 1)[-1]
        matches = self._by_name.get(name, [])
        if "/" in token:
            matches = [p for p in matches if p.endswith("/" + token)]
        return matches[0] if len(matches) == 1 else None

    def mentioned(self, text: str, limit: int = 3) -> list[str]:
        found: list[str] = []
        for token in _PATH_TOKEN.findall(text or ""):
            path = self._resolve(token)
            if path and path not in found:
                found.append(path)
                if len(found) == limit:
                    break
        return found


# ---- orientation tasks (used when a repo has too few suitable issues) ---------------------------------------------

_LOW_VALUE_DIRS = {"docs", "doc", "documentation", "test", "tests", "testing", "example", "examples", "script", "scripts",
                   "benchmark", "benchmarks", ".github"}


def _top_dir(path: str) -> str:
    return path.strip("/").split("/", 1)[0].lower()


def generated_tasks(summary: dict | None, module_map: dict | None, paths: PathIndex,
                    top_imported: tuple[str, int] | None) -> list[dict]:
    """Deterministic 'get oriented' tasks built from the repo's own analysis. No LLM, no invented files."""
    summary, module_map = summary or {}, module_map or {}
    tasks: list[dict] = []

    readme = next((p for p in sorted(paths.paths) if "/" not in p and p.lower().startswith("readme")), None)
    how = (summary.get("how_to_run") or "").strip()
    if how.lower().startswith("not evident"):
        how = ""
    tasks.append({
        "title": "Set up the project and run it locally",
        "summary": plain_summary(how, 240) or "Follow the README to install the dependencies and start the project. "
                                               "Write down every step that was unclear.",
        "related": [readme] if readme else [],
        "reasons": ["Every new developer starts here; no issue needed"],
    })

    entry = next((e for e in module_map.get("entry_points") or [] if e.get("path") in paths.paths), None)
    if entry:
        tasks.append({"title": f"Read the entry point {entry['path']}", "summary": plain_summary(entry.get("reason", "")),
                      "related": [entry["path"]], "reasons": ["Shows where the application starts"]})

    with_files = [m for m in module_map.get("modules") or [] if any(k in paths.paths for k in m.get("key_files", []))]
    # a newcomer should explore the product code first: docs, tests and examples come last
    module = next((m for m in with_files if _top_dir(m.get("path", "")) not in _LOW_VALUE_DIRS), with_files[0] if with_files else None)
    if module:
        keys = [k for k in module["key_files"] if k in paths.paths][:3]
        tasks.append({"title": f"Explore the {module['name']} module", "summary": plain_summary(module.get("purpose", "")),
                      "related": keys, "reasons": ["Gives you the vocabulary of the codebase"]})

    if top_imported and top_imported[0] in paths.paths:
        path, count = top_imported
        tasks.append({"title": f"See what depends on {path}",
                      "summary": f"{path} is imported by {count} other file{'s' if count != 1 else ''}. Open its impact view "
                                 "to see what could break if you changed it, then read two of its dependents.",
                      "related": [path], "reasons": ["The most widely imported file: changes here travel furthest"]})
    return tasks
