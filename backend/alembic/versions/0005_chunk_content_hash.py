"""chunks.content_hash: lets re-indexing reuse embeddings of unchanged chunks

Revision ID: 0005_chunk_content_hash
Revises: 0004_explanations
"""
import sqlalchemy as sa

from alembic import op

revision = "0005_chunk_content_hash"
down_revision = "0004_explanations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Nullable on purpose: rows indexed before this migration have no hash, so their first re-index embeds everything
    # once (and stores hashes); every re-index after that reuses vectors.
    op.add_column("chunks", sa.Column("content_hash", sa.String(64), nullable=True))


def downgrade() -> None:
    op.drop_column("chunks", "content_hash")
