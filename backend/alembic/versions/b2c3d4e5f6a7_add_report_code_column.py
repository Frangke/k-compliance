"""add report_code column to generated_reports

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-04-05 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add column as nullable first
    op.add_column('generated_reports', sa.Column('report_code', sa.String(20), nullable=True))

    # Backfill existing rows: R-YYYYMMDD-NN based on generated_at
    op.execute("""
        UPDATE generated_reports AS gr
        SET report_code = sub.code
        FROM (
            SELECT id,
                   'R-' || to_char(generated_at AT TIME ZONE 'Asia/Seoul', 'YYYYMMDD')
                   || '-' || LPAD(
                       ROW_NUMBER() OVER (
                           PARTITION BY (generated_at AT TIME ZONE 'Asia/Seoul')::date
                           ORDER BY id
                       )::text, 2, '0') AS code
            FROM generated_reports
        ) AS sub
        WHERE gr.id = sub.id
    """)

    # Set NOT NULL + unique constraint
    op.alter_column('generated_reports', 'report_code', nullable=False)
    op.create_unique_constraint('uq_report_code', 'generated_reports', ['report_code'])


def downgrade() -> None:
    op.drop_constraint('uq_report_code', 'generated_reports', type_='unique')
    op.drop_column('generated_reports', 'report_code')
