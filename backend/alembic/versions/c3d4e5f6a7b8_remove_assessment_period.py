"""Remove assessment_period — continuous assessment model

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-04-05 17:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, Sequence[str], None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. ComplianceSnapshot: drop assessment_period
    op.drop_column('compliance_snapshots', 'assessment_period')

    # 2. ChecklistResponse: drop period, recreate unique constraint
    #    Keep only the latest response per checklist_id
    op.execute("""
        DELETE FROM checklist_responses
        WHERE id NOT IN (
            SELECT DISTINCT ON (checklist_id) id
            FROM checklist_responses
            ORDER BY checklist_id, checked_at DESC NULLS LAST, id DESC
        )
    """)
    op.drop_constraint('checklist_responses_checklist_id_period_key', 'checklist_responses', type_='unique')
    op.drop_column('checklist_responses', 'period')
    op.create_unique_constraint('uq_checklist_responses_checklist_id', 'checklist_responses', ['checklist_id'])

    # 3. GeneratedReport: period -> period_start/period_end
    op.add_column('generated_reports', sa.Column('period_start', sa.Date(), nullable=True))
    op.add_column('generated_reports', sa.Column('period_end', sa.Date(), nullable=True))

    # Backfill: convert period string to date range
    op.execute("""
        UPDATE generated_reports SET
            period_start = CASE
                WHEN period LIKE '%-Q1' THEN (LEFT(period, 4) || '-01-01')::date
                WHEN period LIKE '%-Q2' THEN (LEFT(period, 4) || '-04-01')::date
                WHEN period LIKE '%-Q3' THEN (LEFT(period, 4) || '-07-01')::date
                WHEN period LIKE '%-Q4' THEN (LEFT(period, 4) || '-10-01')::date
                WHEN period LIKE '%-H1' THEN (LEFT(period, 4) || '-01-01')::date
                WHEN period LIKE '%-H2' THEN (LEFT(period, 4) || '-07-01')::date
                ELSE (LEFT(period, 4) || '-01-01')::date
            END,
            period_end = CASE
                WHEN period LIKE '%-Q1' THEN (LEFT(period, 4) || '-03-31')::date
                WHEN period LIKE '%-Q2' THEN (LEFT(period, 4) || '-06-30')::date
                WHEN period LIKE '%-Q3' THEN (LEFT(period, 4) || '-09-30')::date
                WHEN period LIKE '%-Q4' THEN (LEFT(period, 4) || '-12-31')::date
                WHEN period LIKE '%-H1' THEN (LEFT(period, 4) || '-06-30')::date
                WHEN period LIKE '%-H2' THEN (LEFT(period, 4) || '-12-31')::date
                ELSE (LEFT(period, 4) || '-12-31')::date
            END
    """)

    op.alter_column('generated_reports', 'period_start', nullable=False)
    op.alter_column('generated_reports', 'period_end', nullable=False)
    op.drop_index('idx_report_type_period', table_name='generated_reports')
    op.drop_column('generated_reports', 'period')
    op.create_index('idx_report_type_period', 'generated_reports', ['report_type', 'period_start', 'period_end'])


def downgrade() -> None:
    # Reverse is lossy — add period back as empty string
    op.drop_index('idx_report_type_period', table_name='generated_reports')
    op.add_column('generated_reports', sa.Column('period', sa.String(20), nullable=True))
    op.execute("""
        UPDATE generated_reports SET period =
            to_char(period_start, 'YYYY') || '-Q' ||
            CASE EXTRACT(QUARTER FROM period_start)
                WHEN 1 THEN '1' WHEN 2 THEN '2' WHEN 3 THEN '3' WHEN 4 THEN '4'
            END
    """)
    op.alter_column('generated_reports', 'period', nullable=False)
    op.drop_column('generated_reports', 'period_start')
    op.drop_column('generated_reports', 'period_end')
    op.create_index('idx_report_type_period', 'generated_reports', ['report_type', 'period'])

    op.drop_constraint('uq_checklist_responses_checklist_id', 'checklist_responses', type_='unique')
    op.add_column('checklist_responses', sa.Column('period', sa.String(20), nullable=True))
    op.execute("UPDATE checklist_responses SET period = '2026-Q1'")
    op.alter_column('checklist_responses', 'period', nullable=False)
    op.create_unique_constraint('checklist_responses_checklist_id_period_key', 'checklist_responses', ['checklist_id', 'period'])

    op.add_column('compliance_snapshots', sa.Column('assessment_period', sa.String(20), nullable=True))
    op.execute("UPDATE compliance_snapshots SET assessment_period = '2026-Q1'")
    op.alter_column('compliance_snapshots', 'assessment_period', nullable=False)
