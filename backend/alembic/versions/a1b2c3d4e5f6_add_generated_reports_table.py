"""add generated_reports table

Revision ID: a1b2c3d4e5f6
Revises: 23a89e8ea2ad
Create Date: 2026-04-05 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '23a89e8ea2ad'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create generated_reports table and enum types."""
    # Use raw SQL for full control over enum + table creation
    op.execute("""
        CREATE TYPE report_type AS ENUM ('isms_assessment', 'corrective_action', 'evidence_summary');
        CREATE TYPE report_status AS ENUM ('generating', 'completed', 'failed');

        CREATE TABLE generated_reports (
            id SERIAL PRIMARY KEY,
            report_type report_type NOT NULL,
            title VARCHAR(300) NOT NULL,
            period VARCHAR(20) NOT NULL,
            status report_status NOT NULL DEFAULT 'generating',
            file_key VARCHAR(500),
            file_size BIGINT,
            error_message TEXT,
            generated_by INTEGER REFERENCES users(id),
            generated_at TIMESTAMPTZ DEFAULT now()
        );

        CREATE INDEX idx_report_type_period ON generated_reports (report_type, period);
    """)


def downgrade() -> None:
    """Drop generated_reports table and enum types."""
    op.drop_index('idx_report_type_period', table_name='generated_reports')
    op.drop_table('generated_reports')
    op.execute("DROP TYPE report_status")
    op.execute("DROP TYPE report_type")
