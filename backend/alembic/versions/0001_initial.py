"""initial schema: repositories, files, symbols, edges, chunks (pgvector + full-text)

Revision ID: 0001
Revises:
"""
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql as pg

from alembic import op
from app.core.config import get_settings

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

DIM = get_settings().embed_dim     # changing the embedding model's size later needs a NEW migration + reindex


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "repositories",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("url", sa.String(500), nullable=False),
        sa.Column("branch", sa.String(100), nullable=False, server_default=""),
        sa.Column("status", sa.String(20), nullable=False, server_default="queued"),
        sa.Column("stage", sa.String(30)),
        sa.Column("error", sa.Text),
        sa.Column("commit_sha", sa.String(40)),
        sa.Column("tech_stack", pg.JSONB),
        sa.Column("module_map", pg.JSONB),
        sa.Column("summary", pg.JSONB),
        sa.Column("index_report", pg.JSONB),
        sa.Column("warnings", pg.JSONB, nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("url", "branch", name="uq_repositories_url_branch"),
    )
    op.create_table(
        "files",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("repo_id", sa.Integer, sa.ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("path", sa.Text, nullable=False),
        sa.Column("language", sa.String(20)),
        sa.Column("size", sa.Integer, nullable=False, server_default="0"),
        sa.Column("sensitive", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.UniqueConstraint("repo_id", "path", name="uq_files_repo_path"),
    )
    op.create_index("ix_files_repo_id", "files", ["repo_id"])
    op.create_table(
        "symbols",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("repo_id", sa.Integer, sa.ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("uid", sa.Text, nullable=False),
        sa.Column("file_path", sa.Text, nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("qualname", sa.Text, nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("start_line", sa.Integer, nullable=False),
        sa.Column("end_line", sa.Integer, nullable=False),
        sa.Column("signature", sa.Text, nullable=False, server_default=""),
        sa.UniqueConstraint("repo_id", "uid", name="uq_symbols_repo_uid"),
    )
    op.create_index("ix_symbols_repo_name", "symbols", ["repo_id", "name"])
    op.create_table(
        "edges",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("repo_id", sa.Integer, sa.ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(10), nullable=False),
        sa.Column("src", sa.Text, nullable=False),
        sa.Column("dst", sa.Text, nullable=False),
    )
    op.create_index("ix_edges_repo_kind", "edges", ["repo_id", "kind"])
    op.create_table(
        "chunks",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("repo_id", sa.Integer, sa.ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("file_path", sa.Text, nullable=False),
        sa.Column("symbol_uid", sa.Text),
        sa.Column("start_line", sa.Integer, nullable=False),
        sa.Column("end_line", sa.Integer, nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("embedding", Vector(DIM), nullable=False),
        sa.Column("content_tsv", pg.TSVECTOR, sa.Computed("to_tsvector('simple', content)", persisted=True)),
    )
    op.create_index("ix_chunks_repo_id", "chunks", ["repo_id"])
    op.create_index("ix_chunks_content_tsv", "chunks", ["content_tsv"], postgresql_using="gin")
    # No ANN (HNSW/IVFFlat) index on purpose: every query is filtered by repo_id and holds <= ~5k rows,
    # so an exact scan is fast AND always returns the full top-k. With pgvector >= 0.8 you can add
    # an HNSW index and enable iterative scans if a single repo ever grows much larger.


def downgrade() -> None:
    for t in ("chunks", "edges", "symbols", "files", "repositories"):
        op.drop_table(t)
