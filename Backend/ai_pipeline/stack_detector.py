"""S1-6: detect languages, frameworks and package managers from manifest files (no LLM)."""
import json, re, posixpath
from pathlib import Path
import xml.etree.ElementTree as ET
from collections import Counter
try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

EXT_LANG = {
    ".py": "Python", ".js": "JavaScript", ".jsx": "JavaScript", ".mjs": "JavaScript", ".cjs": "JavaScript",
    ".ts": "TypeScript", ".tsx": "TypeScript", ".java": "Java", ".kt": "Kotlin", ".go": "Go",
    ".rs": "Rust", ".rb": "Ruby", ".php": "PHP", ".cs": "C#", ".c": "C", ".h": "C",
    ".cpp": "C++", ".cc": "C++", ".hpp": "C++", ".swift": "Swift", ".scala": "Scala", ".dart": "Dart",
}

# dependency name -> framework. A trailing * means "starts with".
FRAMEWORKS = {
    # JavaScript / TypeScript
    "react": "React", "next": "Next.js", "vue": "Vue", "nuxt": "Nuxt", "@angular/core": "Angular",
    "svelte": "Svelte", "express": "Express", "@nestjs/core": "NestJS", "fastify": "Fastify",
    "koa": "Koa", "vite": "Vite", "electron": "Electron", "react-native": "React Native",
    # Python
    "django": "Django", "flask": "Flask", "fastapi": "FastAPI", "streamlit": "Streamlit",
    "tornado": "Tornado", "scrapy": "Scrapy", "torch": "PyTorch", "tensorflow": "TensorFlow",
    "langchain": "LangChain", "pytest": "pytest",
    # Java / Kotlin
    "spring-boot*": "Spring Boot", "spring-webmvc": "Spring MVC", "quarkus*": "Quarkus",
    "micronaut*": "Micronaut", "hibernate-core": "Hibernate",
    # Go
    "github.com/gin-gonic/gin": "Gin", "github.com/labstack/echo*": "Echo", "github.com/gofiber/fiber*": "Fiber",
    # Rust
    "actix-web": "Actix Web", "rocket": "Rocket", "axum": "Axum", "tokio": "Tokio",
    # PHP
    "laravel/framework": "Laravel", "symfony/framework-bundle": "Symfony",
    # Ruby
    "rails": "Ruby on Rails", "sinatra": "Sinatra",
    # .NET
    "microsoft.aspnetcore*": "ASP.NET Core",
}

def match_frameworks(dep_names):
    found = set()
    for dep in dep_names:
        d = dep.lower()
        for key, fw in FRAMEWORKS.items():
            if d == key or (key.endswith("*") and d.startswith(key[:-1])):
                found.add(fw)
    return sorted(found)

def _strip_ns(root):
    for el in root.iter():
        if isinstance(el.tag, str) and "}" in el.tag:
            el.tag = el.tag.split("}", 1)[1]
    return root

# --- one small parser per manifest type; each returns language, package_manager, deps ---
def parse_package_json(text, rel, files):
    data = json.loads(text)
    deps = list(data.get("dependencies", {})) + list(data.get("devDependencies", {}))
    folder = posixpath.dirname(rel)
    has = lambda n: posixpath.join(folder, n) in files or n in files
    if has("pnpm-lock.yaml"): pm = "pnpm"
    elif has("yarn.lock"): pm = "Yarn"
    elif has("bun.lockb") or has("bun.lock"): pm = "Bun"
    else: pm = "npm"
    lang = "TypeScript" if ("typescript" in deps or has("tsconfig.json")) else "JavaScript"
    return {"language": lang, "package_manager": pm, "deps": deps}

def parse_requirements(text, rel, files):
    deps = []
    for line in text.splitlines():
        line = line.split("#")[0].strip()
        if not line or line.startswith("-"):
            continue
        deps.append(re.split(r"[<>=!~\[;@ ]", line)[0])
    return {"language": "Python", "package_manager": "pip", "deps": deps}

def parse_pyproject(text, rel, files):
    data = tomllib.loads(text)
    deps = [re.split(r"[<>=!~\[;@ ]", d.strip())[0] for d in data.get("project", {}).get("dependencies", [])]
    for group in data.get("project", {}).get("optional-dependencies", {}).values():
        deps += [re.split(r"[<>=!~\[;@ ]", d.strip())[0] for d in group]
    tool = data.get("tool", {})
    deps += [k for k in tool.get("poetry", {}).get("dependencies", {}) if k.lower() != "python"]
    pm = "Poetry" if "poetry" in tool else "PDM" if "pdm" in tool else "uv" if "uv" in tool else "pip"
    return {"language": "Python", "package_manager": pm, "deps": deps}

def parse_pipfile(text, rel, files):
    data = tomllib.loads(text)
    return {"language": "Python", "package_manager": "Pipenv",
            "deps": list(data.get("packages", {})) + list(data.get("dev-packages", {}))}

def parse_pom(text, rel, files):
    root = _strip_ns(ET.fromstring(text))
    return {"language": "Java", "package_manager": "Maven",
            "deps": [e.text.strip() for e in root.iter("artifactId") if e.text]}

def parse_gradle(text, rel, files):
    deps = []
    for m in re.finditer(r"""['"]([\w.\-]+):([\w.\-]+)(?::[^'"]*)?['"]""", text):
        deps += [m.group(2), f"{m.group(1)}:{m.group(2)}"]
    lang = "Kotlin" if rel.endswith(".kts") or "kotlin" in text.lower() else "Java"
    return {"language": lang, "package_manager": "Gradle", "deps": deps}

def parse_go_mod(text, rel, files):
    deps = re.findall(r"^\s*(?:require\s+)?([\w.\-]+\.[\w.\-]+/[\w.\-/]+)\s+v[\w.\-+]+", text, re.M)
    return {"language": "Go", "package_manager": "Go modules", "deps": deps}

def parse_cargo(text, rel, files):
    data = tomllib.loads(text)
    return {"language": "Rust", "package_manager": "Cargo",
            "deps": list(data.get("dependencies", {})) + list(data.get("dev-dependencies", {}))}

def parse_composer(text, rel, files):
    data = json.loads(text)
    return {"language": "PHP", "package_manager": "Composer",
            "deps": list(data.get("require", {})) + list(data.get("require-dev", {}))}

def parse_gemfile(text, rel, files):
    return {"language": "Ruby", "package_manager": "Bundler",
            "deps": re.findall(r"""^\s*gem\s+['"]([^'"]+)['"]""", text, re.M)}

def parse_csproj(text, rel, files):
    root = _strip_ns(ET.fromstring(text))
    return {"language": "C#", "package_manager": "NuGet",
            "deps": [e.get("Include") for e in root.iter("PackageReference") if e.get("Include")]}

def parser_for(name):
    if name == "package.json": return parse_package_json
    if name.startswith("requirements") and name.endswith(".txt"): return parse_requirements
    if name == "pyproject.toml": return parse_pyproject
    if name == "Pipfile": return parse_pipfile
    if name == "pom.xml": return parse_pom
    if name in ("build.gradle", "build.gradle.kts"): return parse_gradle
    if name == "go.mod": return parse_go_mod
    if name == "Cargo.toml": return parse_cargo
    if name == "composer.json": return parse_composer
    if name == "Gemfile": return parse_gemfile
    if name.endswith(".csproj"): return parse_csproj
    return None

def detect_tech_stack(root, all_files, max_manifests=100):
    files, manifests = set(all_files), []
    for rel in all_files:
        parser = parser_for(posixpath.basename(rel))
        if not parser:
            continue
        if len(manifests) >= max_manifests:
            break
        try:
            info = parser((Path(root) / rel).read_text(encoding="utf-8", errors="ignore"), rel, files)
            manifests.append({"path": rel, "language": info["language"],
                              "package_manager": info["package_manager"],
                              "frameworks": match_frameworks(info["deps"])})
        except Exception as e:
            manifests.append({"path": rel, "error": f"could not parse ({type(e).__name__})"})

    ext_counts = Counter(EXT_LANG[Path(f).suffix.lower()] for f in all_files if Path(f).suffix.lower() in EXT_LANG)
    total = sum(ext_counts.values())
    languages = [l for l, c in ext_counts.most_common() if c / total >= 0.05] if total else []
    for m in manifests:
        if m.get("language") and m["language"] not in languages:
            languages.append(m["language"])

    return {
        "languages": languages,
        "frameworks": sorted({fw for m in manifests for fw in m.get("frameworks", [])}),
        "package_managers": sorted({m["package_manager"] for m in manifests if m.get("package_manager")}),
        "language_file_counts": dict(ext_counts.most_common()),
        "manifests": manifests,
    }
