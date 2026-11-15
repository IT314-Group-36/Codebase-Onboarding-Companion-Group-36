"""task_progress: each user's progress on the first-week tasks, saved on the server

Revision ID: 0006_task_progress
Revises: 0005_chunk_content_hash
"""
import sqlalchemy as sa

from alembic import op

revision = "0006_task_progress"
down_revision = "0005_chunk_content_hash"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "task_progress",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("repo_id", sa.Integer, sa.ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("task_key", sa.String(80), nullable=False),
        sa.Column("status", sa.String(12), nullable=False, server_default="pending"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_id", "repo_id", "task_key", name="uq_task_progress_user_repo_key"),
    )
    op.create_index("ix_task_progress_user_id", "task_progress", ["user_id"])
    op.create_index("ix_task_progress_repo_id", "task_progress", ["repo_id"])


def downgrade() -> None:
    op.drop_table("task_progress")
