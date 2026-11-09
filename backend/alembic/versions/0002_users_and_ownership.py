"""users table and repository ownership

Adds `users` (GitHub accounts, token stored encrypted) and `repositories.owner_id`.
Uniqueness changes from (url, branch) to (owner_id, url, branch); repos that already exist keep
owner_id NULL and keep the old url+branch rule through a partial unique index.

Revision ID: 0002
Revises: 0001
"""
import sqlalchemy as sa

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("github_id", sa.BigInteger, nullable=False),
        sa.Column("login", sa.String(100), nullable=False),
        sa.Column("name", sa.String(200)),
        sa.Column("email", sa.String(320)),
        sa.Column("avatar_url", sa.String(500)),
        sa.Column("encrypted_access_token", sa.Text),
        sa.Column("token_scopes", sa.String(200)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("github_id", name="uq_users_github_id"),
    )
    op.add_column("repositories", sa.Column(
        "owner_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE", name="fk_repositories_owner_id_users")))
    op.create_index("ix_repositories_owner_id", "repositories", ["owner_id"])
    op.drop_constraint("uq_repositories_url_branch", "repositories", type_="unique")
    op.create_unique_constraint("uq_repositories_owner_url_branch", "repositories", ["owner_id", "url", "branch"])
    op.create_index("uq_repositories_unowned_url_branch", "repositories", ["url", "branch"],
                    unique=True, postgresql_where=sa.text("owner_id IS NULL"))


def downgrade() -> None:
    # Going back to one row per (url, branch): if several users indexed the same repo, keep the oldest copy
    # (the others' derived data is deleted with them). Users and ownership are dropped.
    op.execute("DELETE FROM repositories a USING repositories b "
               "WHERE a.url = b.url AND a.branch = b.branch AND a.id > b.id")
    op.drop_index("uq_repositories_unowned_url_branch", table_name="repositories")
    op.drop_constraint("uq_repositories_owner_url_branch", "repositories", type_="unique")
    op.create_unique_constraint("uq_repositories_url_branch", "repositories", ["url", "branch"])
    op.drop_index("ix_repositories_owner_id", table_name="repositories")
    op.drop_column("repositories", "owner_id")
    op.drop_table("users")
