"""Static analysis: extracts symbols, imports and a heuristic summary per file."""
import ast
import posixpath
import re
from dataclasses import dataclass, field
from pathlib import PurePosixPath

LANG_BY_EXT = {
    ".py": "python", ".js": "javascript", ".jsx": "javascript", ".mjs": "javascript",
    ".ts": "typescript", ".tsx": "typescript", ".java": "java", ".go": "go", ".rs": "rust",
    ".rb": "ruby", ".php": "php", ".cs": "csharp", ".cpp": "cpp", ".c": "c", ".h": "c",
    ".kt": "kotlin", ".swift": "swift", ".sql": "sql", ".sh": "shell",
    ".html": "html", ".css": "css", ".md": "markdown", ".json": "json",
    ".yml": "yaml", ".yaml": "yaml", ".toml": "toml",
}
NON_CODE = {"markdown", "json", "yaml", "toml", "html", "css", "other"}

ImportRef = tuple[str, tuple[str, ...]]  # (module, imported names)


@dataclass
class SymbolInfo:
    name: str
    kind: str
    line: int
    signature: str | None = None
    docstring: str | None = None


@dataclass
class FileAnalysis:
    language: str
    line_count: int
    symbols: list[SymbolInfo] = field(default_factory=list)
    imports: list[ImportRef] = field(default_factory=list)
    docstring: str | None = None


def detect_language(path: str) -> str:
    return LANG_BY_EXT.get(posixpath.splitext(path)[1].lower(), "other")


def _short(doc: str | None, limit: int = 300) -> str | None:
    if not doc:
        return None
    first_para = doc.strip().split("\n\n")[0]
    return " ".join(first_para.split())[:limit] or None


# ---------------- Python ----------------
def _collect(node: ast.AST, out: list[SymbolInfo], prefix: str = "") -> None:
    if isinstance(node, ast.ClassDef):
        out.append(SymbolInfo(prefix + node.name, "class", node.lineno,
                              f"class {node.name}", _short(ast.get_docstring(node))))
        for child in node.body:
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                _collect(child, out, prefix=f"{node.name}.")
    elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        kw = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
        out.append(SymbolInfo(prefix + node.name, "method" if prefix else "function", node.lineno,
                              f"{kw} {node.name}({ast.unparse(node.args)})", _short(ast.get_docstring(node))))


def analyze_python(text: str):
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return [], [], None
    symbols: list[SymbolInfo] = []
    for node in tree.body:
        _collect(node, symbols)
    imports: list[ImportRef] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports += [(a.name, ()) for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            base = "." * node.level + (node.module or "")
            imports.append((base, tuple(a.name for a in node.names if a.name != "*")))
    return symbols, imports, _short(ast.get_docstring(tree))


# ---------------- JS / TS ----------------
_JS_FROM = re.compile(r"""(?:from|import)\s+['"]([^'"]+)['"]""")
_JS_REQ = re.compile(r"""require\(\s*['"]([^'"]+)['"]\s*\)""")
_JS_FUNC = re.compile(r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s*\*?\s*(\w+)\s*\(([^)]*)\)")
_JS_CLASS = re.compile(r"^\s*(?:export\s+)?(?:default\s+)?(?:abstract\s+)?class\s+(\w+)")
_JS_ARROW = re.compile(r"^\s*(?:export\s+)?const\s+(\w+)\s*(?::[^=]+)?=\s*(?:async\s*)?(?:\([^)]*\)|\w+)\s*(?::[^=]+)?=>")


def analyze_js(text: str):
    symbols: list[SymbolInfo] = []
    for i, line in enumerate(text.splitlines(), 1):
        if m := _JS_FUNC.match(line):
            symbols.append(SymbolInfo(m[1], "function", i, f"function {m[1]}({m[2].strip()})"))
        elif m := _JS_CLASS.match(line):
            symbols.append(SymbolInfo(m[1], "class", i, f"class {m[1]}"))
        elif m := _JS_ARROW.match(line):
            symbols.append(SymbolInfo(m[1], "function", i, f"const {m[1]} = (...) =>"))
    specs = list(dict.fromkeys(_JS_FROM.findall(text) + _JS_REQ.findall(text)))
    return symbols, [(s, ()) for s in specs], None


def analyze_file(path: str, text: str) -> FileAnalysis:
    lang = detect_language(path)
    lines = text.count("\n") + (1 if text and not text.endswith("\n") else 0)
    a = FileAnalysis(language=lang, line_count=lines)
    if lang == "python":
        a.symbols, a.imports, a.docstring = analyze_python(text)
    elif lang in ("javascript", "typescript"):
        a.symbols, a.imports, a.docstring = analyze_js(text)
    return a


# ---------------- Import resolution ----------------
def _join(base: str, name: str) -> str:
    return f"{base}/{name}" if base else name


def _ancestors(path: str) -> list[str]:
    parent = PurePosixPath(path).parent
    return ["" if str(p) == "." else str(p) for p in [parent, *parent.parents]]


def resolve_python(source: str, module: str, names: tuple[str, ...], path_set: set[str]) -> list[str]:
    if module.startswith("."):
        level = len(module) - len(module.lstrip("."))
        rest = module.lstrip(".").replace(".", "/")
        base_dir = PurePosixPath(source).parent
        for _ in range(level - 1):
            base_dir = base_dir.parent
        b = "" if str(base_dir) == "." else str(base_dir)
        bases = [_join(b, rest)] if rest else [b]
    else:
        rel = module.replace(".", "/")
        bases = [_join(a, rel) for a in _ancestors(source)] + [_join("src", rel)]
    found: list[str] = []
    for base in bases:
        for n in names:
            for cand in (_join(base, n) + ".py", _join(base, n) + "/__init__.py"):
                if cand in path_set:
                    found.append(cand)
        if base:
            for cand in (base + ".py", base + "/__init__.py"):
                if cand in path_set:
                    found.append(cand)
    return list(dict.fromkeys(f for f in found if f != source))


_JS_EXTS = (".js", ".jsx", ".ts", ".tsx", ".mjs")


def resolve_js(source: str, spec: str, path_set: set[str]) -> list[str]:
    if spec.startswith("."):
        bases = [posixpath.normpath(posixpath.join(posixpath.dirname(source), spec))]
    elif spec.startswith(("@/", "~/")):
        bases = [f"src/{spec[2:]}", spec[2:]]
    else:
        return []
    for b in bases:
        if b in path_set:
            return [b]
        for ext in _JS_EXTS:
            if b + ext in path_set:
                return [b + ext]
        for ext in _JS_EXTS:
            if f"{b}/index{ext}" in path_set:
                return [f"{b}/index{ext}"]
    return []


def resolve_import(source: str, language: str, module: str, names: tuple[str, ...], path_set: set[str]) -> list[str]:
    if language == "python":
        return resolve_python(source, module, names, path_set)
    if language in ("javascript", "typescript"):
        return resolve_js(source, module, path_set)
    return []


# ---------------- Modules & summaries ----------------
CONTAINER_DIRS = {"src", "app", "lib", "packages", "apps", "backend", "frontend", "server", "client"}


def module_for(path: str) -> str:
    parts = path.split("/")
    if len(parts) == 1:
        return "(root)"
    i = 0
    while i < len(parts) - 2 and parts[i] in CONTAINER_DIRS and parts[i + 1] in CONTAINER_DIRS:
        i += 1
    if parts[i] in CONTAINER_DIRS and len(parts) - i > 2:
        return "/".join(parts[: i + 2])
    return "/".join(parts[: i + 1])


ROLE_HINTS = {
    "frontend": "Frontend web app", "backend": "Backend API service", "ai_engine": "AI engine service",
    "app": "Application package (entry point, config, DB wiring)", "js": "Frontend JavaScript (UI logic)",
    "css": "Styles", "client": "Client application", "server": "Server application",
    "api": "HTTP API layer (routes / endpoints)", "routes": "HTTP routes / endpoints",
    "routers": "HTTP routers / endpoints", "controllers": "Request controllers",
    "views": "Views / request handlers", "models": "Data models / database schema",
    "schemas": "Request/response schemas", "services": "Business logic / service layer",
    "utils": "Shared helper utilities", "helpers": "Shared helper utilities",
    "tests": "Automated tests", "test": "Automated tests", "docs": "Documentation",
    "components": "UI components", "pages": "Pages / screens", "hooks": "Reusable UI hooks",
    "migrations": "Database migrations", "config": "Configuration", "core": "Core / shared foundations",
    "db": "Database access", "database": "Database access", "auth": "Authentication & authorization",
    "payments": "Payment processing", "billing": "Billing logic", "scripts": "Helper scripts",
    "public": "Static assets", "static": "Static assets", "templates": "HTML templates",
    "middleware": "Request middleware", "tasks": "Background / async jobs", "workers": "Background workers",
}


def describe_module(name: str, files: list, langs: list[str]) -> str:
    key = name.split("/")[-1].lower()
    role = ROLE_HINTS.get(key)
    lang_txt = f" Mostly {', '.join(langs)}." if langs else ""
    base = role or "Application code" if name != "(root)" else "Project root: entry points, config and docs"
    return f"{base}. {len(files)} file{'s' if len(files) != 1 else ''}.{lang_txt}"


def heuristic_summary(path: str, a: FileAnalysis) -> str:
    if a.docstring:
        return a.docstring
    classes = [s.name for s in a.symbols if s.kind == "class"]
    funcs = [s.name for s in a.symbols if s.kind == "function"]
    parts = []
    if classes:
        parts.append(f"Defines {len(classes)} class(es): {', '.join(classes[:3])}")
    if funcs:
        parts.append(f"{len(funcs)} function(s): {', '.join(funcs[:3])}")
    if parts:
        return "; ".join(parts) + "."
    return f"{a.language} file, {a.line_count} lines."
