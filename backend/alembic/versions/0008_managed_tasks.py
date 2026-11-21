"""Persist manual, AI and GitHub tasks with durable duplicate-prevention tombstones."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = '0008_managed_tasks'
down_revision = '0007_conversations'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('managed_tasks',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('user_id', sa.Integer, sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('repo_id', sa.Integer, sa.ForeignKey('repositories.id', ondelete='CASCADE'), nullable=False),
        sa.Column('key', sa.String(80), nullable=False),
        sa.Column('source', sa.String(12), nullable=False),
        sa.Column('title', sa.String(200), nullable=False),
        sa.Column('description', sa.Text, nullable=False),
        sa.Column('difficulty', sa.String(8), nullable=False),
        sa.Column('related_files', JSONB, nullable=False, server_default='[]'),
        sa.Column('status', sa.String(12), nullable=False, server_default='pending'),
        sa.Column('deleted', sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column('fingerprint', sa.String(250), nullable=False),
        sa.Column('issue_number', sa.Integer),
        sa.Column('issue_url', sa.Text),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint('user_id', 'repo_id', 'key', name='uq_managed_task_key'))
    op.create_index('ix_managed_task_scope', 'managed_tasks', ['user_id', 'repo_id'])
    op.create_check_constraint('ck_managed_task_status', 'managed_tasks', "status IN ('pending','in-progress','completed')")
    op.create_check_constraint('ck_managed_task_source', 'managed_tasks', "source IN ('manual','generated','issue')")
    op.create_check_constraint('ck_managed_task_difficulty', 'managed_tasks', "difficulty IN ('easy','medium','hard')")


def downgrade():
    op.drop_table('managed_tasks')
