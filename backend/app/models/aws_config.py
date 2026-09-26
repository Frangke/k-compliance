from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.prowler import RemediationStatus, ScanStatus, remediation_status_enum, scan_status_enum


class ConfigSyncJob(Base):
    __tablename__ = "config_sync_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    cloud_account_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("cloud_accounts.id"))
    conformance_pack: Mapped[str] = mapped_column(String(200), default="Operational-Best-Practices-for-K-ISMS")
    status: Mapped[ScanStatus] = mapped_column(scan_status_enum, nullable=False, default=ScanStatus.pending)
    total_rules: Mapped[int] = mapped_column(Integer, default=0)
    compliant: Mapped[int] = mapped_column(Integer, default=0)
    non_compliant: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    triggered_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ConfigEvaluation(Base):
    __tablename__ = "config_evaluations"

    id: Mapped[int] = mapped_column(primary_key=True)
    sync_job_id: Mapped[int] = mapped_column(Integer, nullable=False)
    config_rule_name: Mapped[str] = mapped_column(String(200), nullable=False)
    compliance_type: Mapped[str] = mapped_column(String(20), nullable=False)  # COMPLIANT, NON_COMPLIANT
    resource_type: Mapped[str | None] = mapped_column(String(200))
    resource_id: Mapped[str | None] = mapped_column(String(500))
    annotation: Mapped[str | None] = mapped_column(Text)

    isms_item_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("isms_items.id"))

    remediation_status: Mapped[RemediationStatus] = mapped_column(
        remediation_status_enum, default=RemediationStatus.open
    )
    remediation_notes: Mapped[str | None] = mapped_column(Text)

    evaluated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("idx_config_eval_rule", "config_rule_name"),
        Index("idx_config_eval_isms", "isms_item_id"),
        Index("idx_config_eval_compliance", "compliance_type"),
    )
