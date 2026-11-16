
"""Persist Q&A conversations and message status.

Revision ID: 0007_conversations
Revises: 0006_task_progress
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0007_conversations"
down_revision = "0006_task_progress"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "conversations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "repo_id",
            sa.Integer(),
            sa.ForeignKey("repositories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "title",
            sa.String(200),
            nullable=False,
            server_default="New conversation",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_index(
        "ix_conversations_user_id", "conversations", ["user_id"]
    )
    op.create_index(
        "ix_conversations_repo_id", "conversations", ["repo_id"]
    )
    op.create_index(
        "ix_conversations_user_repo",
        "conversations",
        ["user_id", "repo_id"],
    )

    op.create_table(
        "conversation_messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "conversation_id",
            sa.Integer(),
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(10), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.String(12),
            nullable=False,
            server_default="completed",
        ),
        sa.Column(
            "citations",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_index(
        "ix_conversation_messages_conversation_id",
        "conversation_messages",
        ["conversation_id"],
    )
    op.create_index(
        "ix_conversation_messages_conversation_created",
        "conversation_messages",
        ["conversation_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("conversation_messages")
    op.drop_table("conversations")
