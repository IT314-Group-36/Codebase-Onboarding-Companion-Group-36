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
    valid = [c.model_dump() for c in ans.citations
             if any(d.metadata["file_path"] == c.path and c.start_line <= d.metadata["end_line"]
                    and c.end_line >= d.metadata["start_line"] for d in docs)]
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
