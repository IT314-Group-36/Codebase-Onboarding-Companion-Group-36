"""Server-side session revocation: users.session_version.

The session cookie carries the version it was issued under. Logout and "log out everywhere" raise the number, so every
cookie issued before that stops working. Existing rows start at 0, and cookies issued before this migration carry no
version (read as 0), so nobody is logged out by the upgrade.

Revision ID: 0008_session_version
Revises: 0007_conversations
"""

import sqlalchemy as sa

from alembic import op

revision = "0008_session_version"
down_revision = "0007_conversations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("session_version", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )


def downgrade() -> None:
    op.drop_column("users", "session_version")
