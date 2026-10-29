"""Repository description: ONE Gemini call that turns README + stack + file tree + the most
relevant code chunks (retrieved from the vector DB) into a structured summary.
Kept to a single, size-capped call on purpose to save tokens."""
import json
from typing import List

from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from .config import GEMINI_MODEL, LLM_MAX_RETRIES, LLM_TIMEOUT_SECONDS
from .module_map import build_tree_summary, read_readme

RETRIEVAL_QUERIES = ["main entry point where the application starts",
                     "core business logic and main features",
                     "configuration, dependencies and how to run the project"]
CHUNKS_PER_QUERY = 3
MAX_CONTEXT_CHARS = 9000


class RepoSummary(BaseModel):
    title: str = Field(description="Project name")
    one_line: str = Field(description="One sentence: what the project is")
    description: str = Field(description="A 1-2 paragraph plain-English description of what the project does and who uses it")
    architecture: str = Field(description="How the code is organised: main folders/modules and how they relate")
    tech_highlights: List[str] = Field(description="Key languages, frameworks and tools actually used")
    key_files: List[str] = Field(description="3-8 most important file paths to read first, exactly as in the file tree")
    how_to_run: str = Field(description="Short setup/run instructions if evident from the provided material, else 'Not evident from the provided files'")


def gather_context(store, k: int = CHUNKS_PER_QUERY) -> str:
    """Pull a few relevant chunks from the vector DB (deduplicated, size-capped)."""
    if store is None:
        return "(vector store not available)"
    seen, parts, total = set(), [], 0
    for q in RETRIEVAL_QUERIES:
        for d in store.similarity_search(q, k=k):
            key = (d.metadata.get("source"), d.metadata.get("start_line"))
            if key in seen:
                continue
            seen.add(key)
            block = f"--- {key[0]} (lines {key[1]}-{d.metadata.get('end_line')}) ---\n{d.page_content}"
            if total + len(block) > MAX_CONTEXT_CHARS:
                return "\n".join(parts)
            parts.append(block)
            total += len(block)
    return "\n".join(parts) or "(no chunks)"


_PROMPT = ChatPromptTemplate.from_messages([
    ("system",
     "You are helping a new developer understand a codebase. Use ONLY the material provided. "
     "If something is not evident, say so instead of guessing. Every file path you output must appear in the file tree."),
    ("human",
     "Tech stack:\n{tech_stack}\n\nREADME (start):\n{readme}\n\nFile tree (deep folders collapsed):\n{tree}\n\n"
     "Relevant code excerpts:\n{context}\n\nWrite the repository summary."),
])


def generate_summary(root, all_files: list[str], tech_stack: dict, store=None) -> tuple[RepoSummary, list[str]]:
    """Returns (summary, warnings). Needs GOOGLE_API_KEY. Invented key_files are removed."""
    from langchain_google_genai import ChatGoogleGenerativeAI
    llm = ChatGoogleGenerativeAI(model=GEMINI_MODEL, temperature=0,
                                 timeout=LLM_TIMEOUT_SECONDS, max_retries=LLM_MAX_RETRIES)
    raw = (_PROMPT | llm.with_structured_output(RepoSummary)).invoke({
        "tech_stack": json.dumps({k: tech_stack[k] for k in ("languages", "frameworks", "package_managers")}),
        "readme": read_readme(root, all_files, limit=3000),
        "tree": build_tree_summary(all_files, max_lines=250),
        "context": gather_context(store),
    })
    files, warnings = set(all_files), []
    good = [f for f in raw.key_files if f in files]
    warnings += [f"removed unknown key file: {f}" for f in raw.key_files if f not in files]
    return raw.model_copy(update={"key_files": good}), warnings
