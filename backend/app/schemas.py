from datetime import datetime

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


class ReindexIn(BaseModel):
    access_token: str | None = Field(default=None, description="GitHub token for private repos (not stored).")


class UserOut(BaseModel):
    """Public view of a user. Never add the token fields here."""
    model_config = ConfigDict(from_attributes=True)
    id: int
    github_id: int
    login: str
    name: str | None
    email: str | None
    avatar_url: str | None
