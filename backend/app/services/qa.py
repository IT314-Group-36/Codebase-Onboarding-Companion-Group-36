from typing import List

from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from ai_pipeline.llm import structured_chain
from ai_pipeline.module_map import SYSTEM as BASE_SYSTEM
from app.services.retrieval import PgHybridRetriever


class LLMCallError(RuntimeError):
    """The chat model call failed (rate limit, network, bad key...). The API turns this into HTTP 502."""


class Citation(BaseModel):
    path: str = Field(description="File path of an excerpt that supports the answer, exactly as shown")
    start_line: int
    end_line: int


class Answer(BaseModel):
    answer: str = Field(description="Plain-English answer for a new developer, grounded only in the excerpts")
    citations: List[Citation]


class ImpactExplanation(BaseModel):
    explanation: str = Field(description="Plain-English explanation of what could break and why")
    suggested_checks: List[str] = Field(description="Short list of things to test or review")


QA_PROMPT = ChatPromptTemplate.from_messages([
    ("system", BASE_SYSTEM + " Answer ONLY from the code excerpts. If they are not enough to answer, say so and "
                             "say what is missing. Cite excerpts by path and line range."),
    ("human", "Question: {question}\n\nCode excerpts:\n{excerpts}"),
])

IMPACT_PROMPT = ChatPromptTemplate.from_messages([
    ("system", BASE_SYSTEM),
    ("human", "A developer wants to change: {target}\n\nCallers found by static analysis (nearest first):\n{callers}\n\n"
              "Affected files:\n{files}\n\nExplain what is likely to break and what to check. "
              "The analysis is approximate (no dynamic dispatch)."),
])


NL_IMPACT_PROMPT = ChatPromptTemplate.from_messages([
    ("system", BASE_SYSTEM + " The impact facts below were computed from the repository's import and call graphs and are "
                             "reliable. Answer ONLY from them: never add callers, files or tests that are not listed. "
                             "Start with a direct answer to the question, then explain why the main items are affected, "
                             "in plain English for someone new to the codebase. The analysis is static, so say so when it matters."),
    ("human", "Developer's question: {question}\n\nAnalysed target: {target}\n\nImpact facts:\n{facts}\n\n"
              "Answer the question and list what to check before making the change."),
])


async def answer_question(llm, embedder, repo_id: int, question: str, k: int = 8) -> dict:
    """retriever -> prompt -> chat model (structured output) -> validated citations."""
    docs = await PgHybridRetriever(repo_id=repo_id, embeddings=embedder, k=k).ainvoke(question)
    if not docs:
        return {"answer": "No indexed code matched this question.", "citations": [], "sources": []}
    excerpts = "\n\n".join(
        f"[{i}] {d.metadata['file_path']} lines {d.metadata['start_line']}-{d.metadata['end_line']}\n{d.page_content}"
        for i, d in enumerate(docs, 1))
    try:
        ans = await structured_chain(QA_PROMPT, llm, Answer).ainvoke({"question": question, "excerpts": excerpts})
    except Exception as e:  # noqa: BLE001
        raise LLMCallError(str(e)) from e
    # A citation must be wholly contained in one retrieved excerpt. Mere overlap allowed
    # the model to cite arbitrary line ranges extending beyond the evidence it actually saw.
    valid = [c.model_dump() for c in ans.citations
             if c.start_line <= c.end_line and any(
                 d.metadata["file_path"] == c.path
                 and c.start_line >= d.metadata["start_line"]
                 and c.end_line <= d.metadata["end_line"]
                 for d in docs)]
    sources = [{k_: d.metadata[k_] for k_ in ("file_path", "symbol_uid", "start_line", "end_line", "score")} for d in docs]
    return {"answer": ans.answer, "citations": valid, "sources": sources}


async def explain_impact(llm, target: str, impact: dict) -> str:
    callers = [f"- {s['qualname']} ({s['path']}:{s['start_line']}), distance {s['distance']}" for s in impact["affected_symbols"][:25]]
    files = [f"- {f['path']} (distance {f['distance']})" for f in impact["affected_files"][:25]]
    try:
        out = await structured_chain(IMPACT_PROMPT, llm, ImpactExplanation).ainvoke({
            "target": target, "callers": "\n".join(callers) or "(none)", "files": "\n".join(files) or "(none)"})
    except Exception as e:  # noqa: BLE001
        raise LLMCallError(str(e)) from e
    return out.explanation + ("\n\nSuggested checks:\n" + "\n".join(f"- {c}" for c in out.suggested_checks) if out.suggested_checks else "")


# ----------------------------------------------------------------------------- file / function explanations
class SymbolNote(BaseModel):
    name: str = Field(description="Function or class name, exactly as listed in the file's symbols")
    note: str = Field(description="One plain-English sentence on what it does")


class FileExplanation(BaseModel):
    summary: str = Field(description="One plain-English sentence: what this file is for")
    explanation: str = Field(description="One to three short paragraphs for a beginner: what the file does and why it exists. "
                                         "Explain any jargon you use.")
    key_symbols: List[SymbolNote] = Field(description="The most important functions/classes in this file (at most 8)")
    how_it_fits: str = Field(description="How this file relates to the files it uses and the files that use it. "
                                         "Use ONLY the relationship facts provided.")


class SymbolExplanation(BaseModel):
    summary: str = Field(description="One plain-English sentence: what this function/class is for")
    explanation: str = Field(description="One to three short paragraphs for a beginner: what it does, step by step, and why")
    inputs_outputs: str = Field(description="What it takes in and what it gives back, or 'Not evident from the code' if unclear")
    how_it_fits: str = Field(description="How it relates to the functions it calls and the functions that call it. "
                                         "Use ONLY the relationship facts provided.")


_EXPLAIN_RULES = (" Write for someone new to this codebase: short sentences, no unexplained jargon. Use ONLY the code, "
                  "relationship facts and project context provided. If something is not evident, say so instead of guessing.")

FILE_EXPLAIN_PROMPT = ChatPromptTemplate.from_messages([
    ("system", BASE_SYSTEM + _EXPLAIN_RULES),
    ("human", "Project: {project}\nModule this file belongs to: {module}\n\nFile: {path}\n\n"
              "Relationship facts (computed from the import and call graphs, reliable):\n{relationships}\n\n"
              "Functions and classes defined in this file:\n{symbols}\n\nCode (may be truncated):\n{code}\n\n"
              "Explain this file."),
])

SYMBOL_EXPLAIN_PROMPT = ChatPromptTemplate.from_messages([
    ("system", BASE_SYSTEM + _EXPLAIN_RULES),
    ("human", "Project: {project}\nModule: {module}\n\nTarget: {target} ({kind}) in {path}\nSignature: {signature}\n\n"
              "Relationship facts (computed from the call graph, reliable):\n{relationships}\n\n"
              "Code (may be truncated):\n{code}\n\nExplain this {kind}."),
])
