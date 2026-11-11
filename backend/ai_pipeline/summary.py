"""Repository description: ONE LLM call from README + stack + tree + the most relevant code chunks
(retrieved by the caller from pgvector). Kept to one size-capped call to save free-tier quota."""
import json
from typing import List

from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from .llm import structured_chain
from .module_map import SYSTEM, build_tree_summary, read_readme

RETRIEVAL_QUERIES = ["main entry point where the application starts",
                     "core business logic and main features",
                     "configuration, dependencies and how to run the project"]
MAX_CONTEXT_CHARS = 9000


class RepoSummary(BaseModel):
    title: str = Field(description="Project name")
    one_line: str = Field(description="One sentence: what the project is")
    description: str = Field(description="A 1-2 paragraph plain-English description of what the project does and who uses it")
    architecture: str = Field(description="How the code is organised: main folders/modules and how they relate")
    tech_highlights: List[str] = Field(description="Key languages, frameworks and tools actually used")
    key_files: List[str] = Field(description="3-8 most important file paths to read first, exactly as in the file tree")
    how_to_run: str = Field(description="Short setup/run instructions if evident from the provided material, else 'Not evident from the provided files'")


def format_context(docs: list[Document], limit: int = MAX_CONTEXT_CHARS) -> str:
    """Retrieved chunks -> deduplicated, size-capped text block."""
    seen, parts, total = set(), [], 0
    for d in docs:
        m = d.metadata
        key = (m["file_path"], m["start_line"])
        if key in seen:
            continue
        seen.add(key)
        block = f"--- {m['file_path']} (lines {m['start_line']}-{m['end_line']}) ---\n{d.page_content}"
        if total + len(block) > limit:
            break
        parts.append(block)
        total += len(block)
    return "\n".join(parts) or "(no chunks)"


_PROMPT = ChatPromptTemplate.from_messages([
    ("system", SYSTEM + " If something is not evident, say so instead of guessing."),
    ("human", "Tech stack:\n{tech_stack}\n\nREADME (start):\n{readme}\n\n"
              "File tree (deep folders collapsed):\n{tree}\n\nRelevant code excerpts:\n{context}\n\n"
              "Write the repository summary."),
])


async def generate_summary(llm, root, all_files: list[str], tech_stack: dict, context: str) -> tuple[RepoSummary, list[str]]:
    raw = await structured_chain(_PROMPT, llm, RepoSummary).ainvoke({
        "tech_stack": json.dumps({k: tech_stack[k] for k in ("languages", "frameworks", "package_managers")}),
        "readme": read_readme(root, all_files, limit=3000),
        "tree": build_tree_summary(all_files, max_lines=250),
        "context": context,
    })
    files = set(all_files)
    warnings = [f"removed unknown key file: {f}" for f in raw.key_files if f not in files]
    return raw.model_copy(update={"key_files": [f for f in raw.key_files if f in files]}), warnings
