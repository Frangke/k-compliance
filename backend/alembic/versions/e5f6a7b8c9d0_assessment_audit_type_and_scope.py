"""Assessment audit_type + scope (initial/surveillance/renewal)

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-05-05 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, Sequence[str], None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. New enum types — create via raw SQL so the subsequent ADD COLUMN
    #    can reference them with create_type=False (same gotcha as
    #    d4e5f6a7b8c9: sa.Enum inside add_column otherwise tries to CREATE
    #    TYPE a second time).
    op.execute("CREATE TYPE audit_type AS ENUM ('initial', 'surveillance', 'renewal')")
    op.execute("CREATE TYPE scope_mode AS ENUM ('all_items', 'subset')")

    from sqlalchemy.dialects import postgresql
    audit_type_col = postgresql.ENUM(
        'initial', 'surveillance', 'renewal', name='audit_type', create_type=False,
    )
    scope_mode_col = postgresql.ENUM(
        'all_items', 'subset', name='scope_mode', create_type=False,
    )

    # 2. Extend assessments with new columns.
    #    Existing rows default to initial/all_items — closest to "legacy full
    #    round" semantics.
    op.add_column('assessments', sa.Column('audit_type', audit_type_col, nullable=False, server_default='initial'))
    op.add_column('assessments', sa.Column('scope_mode', scope_mode_col, nullable=False, server_default='all_items'))
    op.add_column(
        'assessments',
        sa.Column('parent_assessment_id', sa.Integer(),
                  sa.ForeignKey('assessments.id', ondelete='SET NULL'), nullable=True),
    )
    op.create_index('ix_assessments_parent_assessment_id', 'assessments', ['parent_assessment_id'])

    # 3. Scope items table.
    op.create_table(
        'assessment_scope_items',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('assessment_id', sa.Integer(),
                  sa.ForeignKey('assessments.id', ondelete='CASCADE'), nullable=False),
        sa.Column('item_id', sa.Integer(),
                  sa.ForeignKey('isms_items.id', ondelete='CASCADE'), nullable=False),
        sa.Column('is_sample', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.UniqueConstraint('assessment_id', 'item_id', name='uq_scope_item'),
    )
    op.create_index('ix_scope_items_assessment_id', 'assessment_scope_items', ['assessment_id'])


def downgrade() -> None:
    # NOTE: downgrade drops audit_type / scope / parent linkage — the data
    # is lost; remaining snapshots keep their assessment_id but lose the
    # round's structural metadata.
    op.drop_index('ix_scope_items_assessment_id', table_name='assessment_scope_items')
    op.drop_table('assessment_scope_items')

    op.drop_index('ix_assessments_parent_assessment_id', table_name='assessments')
    op.drop_column('assessments', 'parent_assessment_id')
    op.drop_column('assessments', 'scope_mode')
    op.drop_column('assessments', 'audit_type')

    op.execute("DROP TYPE IF EXISTS scope_mode")
    op.execute("DROP TYPE IF EXISTS audit_type")
