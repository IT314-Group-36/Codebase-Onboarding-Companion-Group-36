from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------- Repositories ----------
class RepoCreate(BaseModel):
    source: str = Field(
        ...,
        description="Git URL (https:// or git@) or a local folder path on the server",
        examples=["https://github.com/tiangolo/full-stack-fastapi-template", "."],
    )
    name: str | None = Field(None, description="Display name (derived from source if omitted)")


class RepoOut(ORM):
    id: int
    name: str
    source: str
    status: str
    error: str | None = None
    file_count: int
    created_at: datetime
    indexed_at: datetime | None = None


# ---------- Map / exploration ----------
class FileSummary(ORM):
    path: str
    module: str | None = None
    language: str
    line_count: int
    summary: str | None = None


class SourceOut(BaseModel):
    path: str
    language: str
    content: str
    line_count: int
    truncated: bool


class SymbolOut(ORM):
    name: str
    kind: str
    line: int
    file_path: str
    signature: str | None = None
    docstring: str | None = None


class ModuleOut(BaseModel):
    name: str
    description: str
    file_count: int
    line_count: int
    languages: list[str]
    key_files: list[FileSummary]


class RepoMap(BaseModel):
    repo: RepoOut
    modules: list[ModuleOut]


class FileExplanation(BaseModel):
    path: str
    module: str
    language: str
    line_count: int
    summary: str | None
    explanation: str
    used_ai: bool
    provider: str | None = None
    symbols: list[SymbolOut]
    imports: list[str] = Field(description="Internal files this file imports")
    external_imports: list[str] = Field(description="Libraries / unresolved imports")
    imported_by: list[str] = Field(description="Internal files that import this file")


class GraphNode(BaseModel):
    id: str
    label: str
    module: str | None = None
    language: str | None = None


class GraphEdge(BaseModel):
    source: str
    target: str
    weight: int = 1


class Graph(BaseModel):
    level: str
    nodes: list[GraphNode]
    edges: list[GraphEdge]


# ---------- Q&A ----------
class AskRequest(BaseModel):
    question: str = Field(..., min_length=3, examples=["Where is the payment logic handled?"])


class SourceRef(BaseModel):
    path: str
    reason: str
    score: float
    line: int | None = None


class AskResponse(BaseModel):
    question: str
    answer: str
    sources: list[SourceRef]
    used_ai: bool
    provider: str | None = None


class QuestionOut(ORM):
    id: int
    question: str
    answer: str
    sources: list
    created_at: datetime


class ImpactRequest(BaseModel):
    target: str = Field(
        ..., description="A file path or a function/class name", examples=["app/models.py", "index_repository"]
    )


class ImpactResponse(BaseModel):
    target: str
    kind: str  # file | symbol | unknown
    defined_in: list[str]
    directly_affected: list[str]
    transitively_affected: list[str]
    affected_tests: list[str]
    risk: str  # none | low | medium | high
    notes: str


# ---------- Onboarding tasks ----------
class TaskItem(BaseModel):
    title: str
    detail: str | None = None
    source: str  # github | heuristic
    url: str | None = None
    labels: list[str] = []


class DayPlan(BaseModel):
    day: int
    focus: str
    tasks: list[str]


class OnboardingTasks(BaseModel):
    issues: list[TaskItem]
    plan: list[DayPlan]
