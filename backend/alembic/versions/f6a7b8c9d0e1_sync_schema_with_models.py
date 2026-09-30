"""Sync schema with models: cloud account metadata, config sync job link, report types

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-09-30

Columns and enum values that the models (and API) already use but no earlier
migration created. A database built only from `alembic upgrade head` failed on
the dashboard Config summary, cloud account list, ISMS assessment report and
evidence package endpoints.

Every statement is idempotent (IF NOT EXISTS) so databases that already got
these changes by other means upgrade without errors.
"""

from typing import Sequence, Union

from alembic import op

revision: str = 'f6a7b8c9d0e1'
down_revision: Union[str, Sequence[str], None] = 'e5f6a7b8c9d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE report_type ADD VALUE IF NOT EXISTS 'evidence_package'")
    op.execute("ALTER TYPE report_type ADD VALUE IF NOT EXISTS 'dashboard_snapshot'")

    op.execute(
        """
        ALTER TABLE cloud_accounts
            ADD COLUMN IF NOT EXISTS purpose VARCHAR(200),
            ADD COLUMN IF NOT EXISTS admin_name VARCHAR(100),
            ADD COLUMN IF NOT EXISTS admin_email VARCHAR(200),
            ADD COLUMN IF NOT EXISTS auth_type VARCHAR(30) NOT NULL DEFAULT 'instance_role',
            ADD COLUMN IF NOT EXISTS default_region VARCHAR(30) NOT NULL DEFAULT 'ap-northeast-2',
            ADD COLUMN IF NOT EXISTS credentials_last_updated TIMESTAMP WITH TIME ZONE
        """
    )

    op.execute(
        """
        ALTER TABLE config_sync_jobs
            ADD COLUMN IF NOT EXISTS cloud_account_id INTEGER,
            ADD COLUMN IF NOT EXISTS error_message TEXT
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint c
                JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = ANY (c.conkey)
                WHERE c.conrelid = 'config_sync_jobs'::regclass
                  AND c.contype = 'f'
                  AND a.attname = 'cloud_account_id'
            ) THEN
                ALTER TABLE config_sync_jobs
                    ADD CONSTRAINT config_sync_jobs_cloud_account_id_fkey
                    FOREIGN KEY (cloud_account_id) REFERENCES cloud_accounts (id);
            END IF;
        END $$
        """
    )


def downgrade() -> None:
    # PostgreSQL cannot drop enum values; 'evidence_package' and
    # 'dashboard_snapshot' stay in report_type after a downgrade.
    op.execute("ALTER TABLE config_sync_jobs DROP CONSTRAINT IF EXISTS config_sync_jobs_cloud_account_id_fkey")
    op.execute(
        """
        ALTER TABLE config_sync_jobs
            DROP COLUMN IF EXISTS error_message,
            DROP COLUMN IF EXISTS cloud_account_id
        """
    )
    op.execute(
        """
        ALTER TABLE cloud_accounts
            DROP COLUMN IF EXISTS credentials_last_updated,
            DROP COLUMN IF EXISTS default_region,
            DROP COLUMN IF EXISTS auth_type,
            DROP COLUMN IF EXISTS admin_email,
            DROP COLUMN IF EXISTS admin_name,
            DROP COLUMN IF EXISTS purpose
        """
    )
