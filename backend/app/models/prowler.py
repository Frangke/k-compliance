from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, LargeBinary, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import ENUM, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ScanStatus(str, PyEnum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class ScanProvider(str, PyEnum):
    aws = "aws"
    gcp = "gcp"
    azure = "azure"


class FindingStatus(str, PyEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    MANUAL = "MANUAL"


class FindingSeverity(str, PyEnum):
    informational = "informational"
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class RemediationStatus(str, PyEnum):
    open = "open"
    in_progress = "in_progress"
    resolved = "resolved"
    accepted_risk = "accepted_risk"
    false_positive = "false_positive"


scan_status_enum = ENUM(ScanStatus, name="scan_status", create_type=False)
scan_provider_enum = ENUM(ScanProvider, name="scan_provider", create_type=False)
finding_status_enum = ENUM(FindingStatus, name="finding_status", create_type=False)
finding_severity_enum = ENUM(FindingSeverity, name="finding_severity", create_type=False)
remediation_status_enum = ENUM(RemediationStatus, name="remediation_status", create_type=False)


class CloudAccount(Base):
    __tablename__ = "cloud_accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    provider: Mapped[ScanProvider] = mapped_column(scan_provider_enum, nullable=False)
    account_id: Mapped[str] = mapped_column(String(100), nullable=False)
    alias: Mapped[str] = mapped_column(String(200), nullable=False)
    purpose: Mapped[str | None] = mapped_column(String(200))
    admin_name: Mapped[str | None] = mapped_column(String(100))
    admin_email: Mapped[str | None] = mapped_column(String(200))
    # Credential storage. auth_type ∈ instance_role / assume_role / access_key.
    # credentials (AES-256-GCM-encrypted JSON) may contain:
    #   {"role_arn", "external_id"}                     for assume_role
    #   {"access_key_id", "secret_access_key"}          for access_key
    # instance_role has credentials=NULL (uses EC2 instance profile).
    auth_type: Mapped[str] = mapped_column(String(30), nullable=False, default="instance_role")
    credentials: Mapped[bytes | None] = mapped_column(LargeBinary)
    default_region: Mapped[str] = mapped_column(String(30), nullable=False, default="ap-northeast-2")
    credentials_last_updated: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint("provider", "account_id"),)


class ScanJob(Base):
    __tablename__ = "scan_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    cloud_account_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("cloud_accounts.id"))
    provider: Mapped[ScanProvider] = mapped_column(scan_provider_enum, nullable=False, default=ScanProvider.aws)
    compliance: Mapped[str] = mapped_column(String(100), default="kisa_isms_p_2023_aws")

    status: Mapped[ScanStatus] = mapped_column(scan_status_enum, nullable=False, default=ScanStatus.pending)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text)

    total_checks: Mapped[int] = mapped_column(Integer, default=0)
    passed: Mapped[int] = mapped_column(Integer, default=0)
    failed: Mapped[int] = mapped_column(Integer, default=0)

    triggered_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ProwlerFinding(Base):
    __tablename__ = "prowler_findings"

    id: Mapped[int] = mapped_column(primary_key=True)
    scan_job_id: Mapped[int] = mapped_column(Integer, ForeignKey("scan_jobs.id", ondelete="CASCADE"))

    check_id: Mapped[str] = mapped_column(String(200), nullable=False)
    check_title: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[FindingStatus] = mapped_column(finding_status_enum, nullable=False)
    severity: Mapped[FindingSeverity] = mapped_column(finding_severity_enum, nullable=False)

    resource_uid: Mapped[str | None] = mapped_column(String(500))
    resource_type: Mapped[str | None] = mapped_column(String(200))
    resource_region: Mapped[str | None] = mapped_column(String(50))
    resource_details: Mapped[str | None] = mapped_column(Text)

    isms_item_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("isms_items.id"), index=True)

    remediation_status: Mapped[RemediationStatus] = mapped_column(
        remediation_status_enum, default=RemediationStatus.open
    )
    remediation_notes: Mapped[str | None] = mapped_column(Text)
    remediated_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))
    remediated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    raw_json: Mapped[dict | None] = mapped_column(JSONB)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("idx_findings_scan_job", "scan_job_id"),
        Index("idx_findings_status", "status"),
        Index("idx_findings_severity", "severity"),
    )
