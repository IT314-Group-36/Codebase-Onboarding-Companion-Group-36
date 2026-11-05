from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, Computed, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from app.core.config import get_settings
from app.db.base import Base

EMBED_DIM = get_settings().embed_dim


class Repository(Base):
    __tablename__ = "repositories"
    __table_args__ = (UniqueConstraint("url", "branch", name="uq_repositories_url_branch"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    url: Mapped[str] = mapped_column(String(500))
    branch: Mapped[str] = mapped_column(String(100), default="")           # "" = default branch
    status: Mapped[str] = mapped_column(String(20), default="queued")       # queued|indexing|ready|failed
    stage: Mapped[str | None] = mapped_column(String(30))
    error: Mapped[str | None] = mapped_column(Text)
    commit_sha: Mapped[str | None] = mapped_column(String(40))
    tech_stack: Mapped[dict | None] = mapped_column(JSONB)
    module_map: Mapped[dict | None] = mapped_column(JSONB)
    summary: Mapped[dict | None] = mapped_column(JSONB)
    index_report: Mapped[dict | None] = mapped_column(JSONB)
    warnings: Mapped[list] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class File(Base):
    __tablename__ = "files"
    __table_args__ = (UniqueConstraint("repo_id", "path", name="uq_files_repo_path"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    repo_id: Mapped[int] = mapped_column(ForeignKey("repositories.id", ondelete="CASCADE"), index=True)
    path: Mapped[str] = mapped_column(Text)
    language: Mapped[str | None] = mapped_column(String(20))
    size: Mapped[int] = mapped_column(Integer, default=0)
    sensitive: Mapped[bool] = mapped_column(Boolean, default=False)


class Symbol(Base):
    __tablename__ = "symbols"
    __table_args__ = (UniqueConstraint("repo_id", "uid", name="uq_symbols_repo_uid"),
                      Index("ix_symbols_repo_name", "repo_id", "name"))

    id: Mapped[int] = mapped_column(primary_key=True)
    repo_id: Mapped[int] = mapped_column(ForeignKey("repositories.id", ondelete="CASCADE"))
    uid: Mapped[str] = mapped_column(Text)                  # "<path>::<qualname>"
    file_path: Mapped[str] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text)
    qualname: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(20))
    start_line: Mapped[int] = mapped_column(Integer)
    end_line: Mapped[int] = mapped_column(Integer)
    signature: Mapped[str] = mapped_column(Text, default="")


class Edge(Base):
    """kind='imports': src/dst are file paths. kind='calls': src/dst are symbol uids."""
    __tablename__ = "edges"
    __table_args__ = (Index("ix_edges_repo_kind", "repo_id", "kind"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    repo_id: Mapped[int] = mapped_column(ForeignKey("repositories.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(10))
    src: Mapped[str] = mapped_column(Text)
    dst: Mapped[str] = mapped_column(Text)


class Chunk(Base):
    __tablename__ = "chunks"
    __table_args__ = (Index("ix_chunks_content_tsv", "content_tsv", postgresql_using="gin"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    repo_id: Mapped[int] = mapped_column(ForeignKey("repositories.id", ondelete="CASCADE"), index=True)
    file_path: Mapped[str] = mapped_column(Text)
    symbol_uid: Mapped[str | None] = mapped_column(Text)
    start_line: Mapped[int] = mapped_column(Integer)
    end_line: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    embedding = mapped_column(Vector(EMBED_DIM), nullable=False)
    content_tsv = mapped_column(TSVECTOR, Computed("to_tsvector('simple', content)", persisted=True))
