"""explanations: cache for LLM file/function explanations

Revision ID: 0004_explanations
Revises: 0003_issues
"""
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

from alembic import op

revision = "0004_explanations"
down_revision = "0003_issues"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "explanations",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("repo_id", sa.Integer, sa.ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(10), nullable=False),
        sa.Column("target", sa.Text, nullable=False),
        sa.Column("commit_sha", sa.String(40)),
        sa.Column("payload", pg.JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("repo_id", "kind", "target", name="uq_explanations_repo_kind_target"),
    )
    op.create_index("ix_explanations_repo_id", "explanations", ["repo_id"])


def downgrade() -> None:
    op.drop_table("explanations")
