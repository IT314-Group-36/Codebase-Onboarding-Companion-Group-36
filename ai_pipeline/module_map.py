"""S1-8: Gemini returns a schema-enforced JSON module map (Pydantic + with_structured_output)."""
import json
from collections import Counter
from pathlib import Path
from typing import List

from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from .config import GEMINI_MODEL, LLM_MAX_RETRIES, LLM_TIMEOUT_SECONDS


class ModuleInfo(BaseModel):
    name: str = Field(description="Short human-friendly module name, e.g. 'Authentication'")
    path: str = Field(description="Folder or file path of the module, exactly as it appears in the file tree")
    purpose: str = Field(description="One or two plain-English sentences on what this module does")
    key_files: List[str] = Field(description="Most important file paths in this module, exactly as in the file tree")


class EntryPoint(BaseModel):
    path: str = Field(description="File path of the entry point, exactly as in the file tree")
    reason: str = Field(description="Why this file is where execution or the app starts")


class ModuleMap(BaseModel):
    project_summary: str = Field(description="Two to three sentences describing what the project does")
    modules: List[ModuleInfo] = Field(description="The main modules of the codebase (typically 3 to 12)")
    entry_points: List[EntryPoint] = Field(description="Files where the application starts or is invoked")


def build_tree_summary(files: list[str], max_lines: int = 400) -> str:
    def render(depth):
        lines, collapsed = [], Counter()
        for f in files:
            parts = f.split("/")
            if len(parts) <= depth:
                lines.append(f)
            else:
                collapsed["/".join(parts[:depth])] += 1
        lines += [f"{k}/ ... ({n} files inside)" for k, n in collapsed.items()]
        return sorted(lines)
    for depth in range(10, 0, -1):
        lines = render(depth)
        if len(lines) <= max_lines:
            return "\n".join(lines)
    return "\n".join(render(1)[:max_lines])


def read_readme(root, files: list[str], limit: int = 2000) -> str:
    for f in files:
        if "/" not in f and f.lower().startswith("readme"):
            return (Path(root) / f).read_text(encoding="utf-8", errors="ignore")[:limit]
    return "(no README found)"


def validate_paths(mm: ModuleMap, all_files: list[str]) -> tuple[ModuleMap, list[str]]:
    """Remove any path the LLM invented. Returns (clean_map, list_of_warnings).
    A module/entry path is valid if it is a file in the repo or a folder containing files."""
    files = set(all_files)
    folders = {"/".join(f.split("/")[:i]) for f in all_files for i in range(1, len(f.split("/")))}

    def ok(p: str) -> bool:
        p = p.strip().rstrip("/")
        return p in files or p in folders

    warnings = []
    modules = []
    for m in mm.modules:
        if not ok(m.path):
            warnings.append(f"dropped module '{m.name}': path not found: {m.path}")
            continue
        good_keys = [k for k in m.key_files if k in files]
        for k in m.key_files:
            if k not in files:
                warnings.append(f"removed unknown key file in '{m.name}': {k}")
        modules.append(m.model_copy(update={"key_files": good_keys}))
    entries = []
    for e in mm.entry_points:
        if e.path in files:
            entries.append(e)
        else:
            warnings.append(f"dropped entry point: path not found: {e.path}")
    return mm.model_copy(update={"modules": modules, "entry_points": entries}), warnings
  
_PROMPT = ChatPromptTemplate.from_messages([
    ("system",
     "You are a software architecture analyst helping new developers understand a codebase. "
     "Use ONLY the information provided. Every path you output must appear in the file tree below; never invent files."),
    ("human",
     "Detected tech stack:\n{tech_stack}\n\n"
     "README (start):\n{readme}\n\n"
     "File tree (deep folders are collapsed):\n{tree}\n\n"
     "Produce the module map for this repository."),
])


def generate_module_map(root, all_files: list[str], tech_stack: dict) -> tuple[ModuleMap, list[str]]:
    """Returns (validated ModuleMap, warnings). Needs GOOGLE_API_KEY in the environment."""
    from langchain_google_genai import ChatGoogleGenerativeAI
    llm = ChatGoogleGenerativeAI(model=GEMINI_MODEL, temperature=0,
                                 timeout=LLM_TIMEOUT_SECONDS, max_retries=LLM_MAX_RETRIES)
    chain = _PROMPT | llm.with_structured_output(ModuleMap)
    raw = chain.invoke({
        "tech_stack": json.dumps({k: tech_stack[k] for k in ("languages", "frameworks", "package_managers")}),
        "readme": read_readme(root, all_files),
        "tree": build_tree_summary(all_files),
    })
    return validate_paths(raw, all_files)
