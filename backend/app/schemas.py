from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class RepoCreate(BaseModel):
    url: str = Field(description="https://github.com/<owner>/<repo>")
    branch: str = ""
    access_token: str | None = Field(default=None, description="GitHub token for private repos. Used for this job only; never stored in the DB.")


class RepoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    url: str
    branch: str
    status: str
    stage: str | None
    error: str | None
    commit_sha: str | None
    warnings: list
    created_at: datetime
    updated_at: datetime


class RepoDetail(RepoOut):
    tech_stack: dict | None
    summary: dict | None
    index_report: dict | None


class FileOut(BaseModel):
    path: str
    language: str | None
    size: int
    sensitive: bool


class SymbolOut(BaseModel):
    uid: str
    name: str
    qualname: str
    kind: str
    file_path: str
    start_line: int
    end_line: int
    signature: str


class SearchIn(BaseModel):
    query: str = Field(min_length=2, max_length=500)
    k: int = Field(default=8, ge=1, le=20)


class AskIn(BaseModel):
    question: str = Field(min_length=3, max_length=1000)
    # Optional hints for "what would break if I change X?" questions: the UI can pass the symbol/file the user picked
    # (or chose from a clarification list), so the question does not have to name it. Ignored for other questions.
    symbol: str | None = Field(default=None, max_length=500, description="Symbol uid or name the impact question is about")
    file: str | None = Field(default=None, max_length=500, description="File path the impact question is about")
    depth: int | None = Field(default=None, ge=1, le=6, description="How many call/import steps to follow (default 3)")


class ReindexIn(BaseModel):
    access_token: str | None = Field(default=None, description="GitHub token for private repos (not stored).")


class MeOut(BaseModel):
    """The signed-in user as the frontend needs it. `github_connected` says a GitHub token is stored; the token itself never leaves the server."""
    id: int
    github_id: int
    login: str
    name: str | None
    email: str | None
    avatar_url: str | None
    github_connected: bool
    token_scopes: str | None


class GitHubRepoOut(BaseModel):
    full_name: str
    url: str
    private: bool
    default_branch: str | None
    description: str | None
    language: str | None
    updated_at: str | None
    owner: str


class GitHubRepoList(BaseModel):
    repos: list[GitHubRepoOut]
    page: int
    has_more: bool


class BranchList(BaseModel):
    default_branch: str | None
    branches: list[str]
    truncated: bool


class UserOut(BaseModel):
    """Public view of a user. Never add the token fields here."""
    model_config = ConfigDict(from_attributes=True)
    id: int
    github_id: int
    login: str
    name: str | None
    email: str | None
    avatar_url: str | None


class SyncOut(BaseModel):
    status: Literal["never", "queued", "syncing", "ok", "failed"]
    message: str | None = Field(default=None, description="The error when failed, or a note such as 'no labelled issues'.")
    fetched: int = Field(default=0, description="Issues stored by the last successful sync.")
    synced_at: datetime | None = Field(default=None, description="Time of the last SUCCESSFUL sync.")


class RelatedFileOut(BaseModel):
    path: str
    source: Literal["mentioned", "search", "suggested"] = Field(
        description="mentioned: the issue names this file. search: matches the issue text. suggested: orientation task.")


class TaskGuideOut(BaseModel):
    what_to_do: str
    where_to_start: str
    done_when: str


class TaskOut(BaseModel):
    source: Literal["issue", "generated"]
    suggested_day: int = Field(ge=1, le=5)
    title: str
    difficulty: Literal["easy", "medium"]
    summary: str
    number: int | None = None
    url: str | None = None
    labels: list[str] = []
    comments: int | None = None
    score: float | None = None
    reasons: list[str] = []
    related_files: list[RelatedFileOut] = []
    guide: TaskGuideOut | None = Field(default=None, description="Only with ?explain=true.")


class TaskPlanOut(BaseModel):
    repo_id: int
    sync: SyncOut
    eligible_issues: int = Field(description="Synced issues that suit a newcomer (before the limit is applied).")
    fallback_used: bool = Field(description="True when orientation tasks were added because too few issues qualified.")
    notes: list[str]
    tasks: list[TaskOut]

