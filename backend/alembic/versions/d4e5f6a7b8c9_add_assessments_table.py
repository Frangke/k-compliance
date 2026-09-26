"""Add assessments entity + optional links from snapshots/reports (P1-2)

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-05-05 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, Sequence[str], None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create the enum type explicitly via raw SQL so SQLAlchemy's Column
    #    layer doesn't try to auto-create it again during create_table.
    op.execute("CREATE TYPE assessment_status AS ENUM ('draft', 'active', 'closed')")

    # 2. assessments table — use postgresql.ENUM with create_type=False so the
    #    column just references the existing type.
    from sqlalchemy.dialects import postgresql
    status_col = postgresql.ENUM(
        'draft', 'active', 'closed', name='assessment_status', create_type=False,
    )
    op.create_table(
        'assessments',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('code', sa.String(50), nullable=False, unique=True),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('framework', sa.String(50), nullable=False, server_default='kisa_isms_p_2023'),
        sa.Column('period_start', sa.Date(), nullable=False),
        sa.Column('period_end', sa.Date(), nullable=False),
        sa.Column('scope_note', sa.Text()),
        sa.Column('status', status_col, nullable=False, server_default='draft'),
        sa.Column('created_by', sa.Integer(), sa.ForeignKey('users.id')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('closed_at', sa.DateTime(timezone=True)),
    )
    op.create_index('idx_assessment_period', 'assessments', ['period_start', 'period_end'])
    op.create_index('idx_assessment_status', 'assessments', ['status'])

    # 3. FK columns on existing tables — both nullable so legacy rows survive.
    op.add_column(
        'compliance_snapshots',
        sa.Column('assessment_id', sa.Integer(), sa.ForeignKey('assessments.id', ondelete='SET NULL'), nullable=True),
    )
    op.create_index('ix_compliance_snapshots_assessment_id', 'compliance_snapshots', ['assessment_id'])

    op.add_column(
        'generated_reports',
        sa.Column('assessment_id', sa.Integer(), sa.ForeignKey('assessments.id', ondelete='SET NULL'), nullable=True),
    )
    op.create_index('ix_generated_reports_assessment_id', 'generated_reports', ['assessment_id'])


def downgrade() -> None:
    # NOTE: downgrade is lossy — any snapshots/reports that were associated
    # to an assessment lose that linkage.
    op.drop_index('ix_generated_reports_assessment_id', table_name='generated_reports')
    op.drop_column('generated_reports', 'assessment_id')

    op.drop_index('ix_compliance_snapshots_assessment_id', table_name='compliance_snapshots')
    op.drop_column('compliance_snapshots', 'assessment_id')

    op.drop_index('idx_assessment_status', table_name='assessments')
    op.drop_index('idx_assessment_period', table_name='assessments')
    op.drop_table('assessments')

    op.execute("DROP TYPE IF EXISTS assessment_status")
