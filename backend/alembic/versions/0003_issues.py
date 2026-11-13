"""issues + issue_syncs: GitHub issues cache for the first-week task list

Revision ID: 0003_issues
Revises: 0002
"""
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

from alembic import op

revision = "0003_issues"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "issues",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("repo_id", sa.Integer, sa.ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("number", sa.Integer, nullable=False),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("body", sa.Text, nullable=False, server_default=""),
        sa.Column("labels", pg.JSONB, nullable=False, server_default="[]"),
        sa.Column("url", sa.Text, nullable=False, server_default=""),
        sa.Column("comments", sa.Integer, nullable=False, server_default="0"),
        sa.Column("assignees", sa.Integer, nullable=False, server_default="0"),
        sa.Column("locked", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("gh_created_at", sa.DateTime(timezone=True)),
        sa.Column("gh_updated_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("repo_id", "number", name="uq_issues_repo_number"),
    )
    op.create_index("ix_issues_repo_id", "issues", ["repo_id"])
    op.create_table(
        "issue_syncs",
        sa.Column("repo_id", sa.Integer, sa.ForeignKey("repositories.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("status", sa.String(10), nullable=False, server_default="queued"),
        sa.Column("message", sa.Text),
        sa.Column("fetched", sa.Integer, nullable=False, server_default="0"),
        sa.Column("synced_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("issue_syncs")
    op.drop_table("issues")
