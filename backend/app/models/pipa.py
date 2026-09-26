from datetime import date, datetime
from enum import Enum as PyEnum

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import ENUM
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


# === Consent ===
class ConsentTemplate(Base):
    __tablename__ = "consent_templates"

    id: Mapped[int] = mapped_column(primary_key=True)
    purpose: Mapped[str] = mapped_column(String(300), nullable=False)
    legal_basis: Mapped[str] = mapped_column(String(100), nullable=False)
    data_categories: Mapped[str] = mapped_column(Text, nullable=False)
    retention_period: Mapped[str | None] = mapped_column(String(100))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ConsentVersion(Base):
    __tablename__ = "consent_versions"

    id: Mapped[int] = mapped_column(primary_key=True)
    template_id: Mapped[int] = mapped_column(Integer, ForeignKey("consent_templates.id"))
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    effective_date: Mapped[date] = mapped_column(Date, nullable=False)
    is_published: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint("template_id", "version_number"),)


# === DSR ===
class DSRType(str, PyEnum):
    access = "access"
    correction = "correction"
    deletion = "deletion"
    suspension = "suspension"


class DSRStatus(str, PyEnum):
    received = "received"
    assigned = "assigned"
    processing = "processing"
    completed = "completed"
    rejected = "rejected"
    overdue = "overdue"


dsr_type_enum = ENUM(DSRType, name="dsr_type", create_type=False)
dsr_status_enum = ENUM(DSRStatus, name="dsr_status", create_type=False)


class DSRRequest(Base):
    __tablename__ = "dsr_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    request_type: Mapped[DSRType] = mapped_column(dsr_type_enum, nullable=False)
    requester_name: Mapped[str] = mapped_column(String(100), nullable=False)
    requester_contact: Mapped[str | None] = mapped_column(String(200))
    requester_id_type: Mapped[str | None] = mapped_column(String(50))
    description: Mapped[str] = mapped_column(Text, nullable=False)

    status: Mapped[DSRStatus] = mapped_column(dsr_status_enum, nullable=False, default=DSRStatus.received)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    assigned_to: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))

    result_description: Mapped[str | None] = mapped_column(Text)
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (Index("idx_dsr_status", "status"), Index("idx_dsr_due_date", "due_date"))


# === Destruction ===
class DestructionStatus(str, PyEnum):
    scheduled = "scheduled"
    in_progress = "in_progress"
    completed = "completed"
    verified = "verified"
    overdue = "overdue"


destruction_status_enum = ENUM(DestructionStatus, name="destruction_status", create_type=False)


class DestructionRecord(Base):
    __tablename__ = "destruction_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    data_category: Mapped[str] = mapped_column(String(200), nullable=False)
    data_description: Mapped[str | None] = mapped_column(Text)
    data_volume: Mapped[str | None] = mapped_column(String(100))
    retention_basis: Mapped[str | None] = mapped_column(String(200))
    retention_expiry: Mapped[date] = mapped_column(Date, nullable=False)

    scheduled_date: Mapped[date] = mapped_column(Date, nullable=False)
    actual_date: Mapped[date | None] = mapped_column(Date)
    method: Mapped[str | None] = mapped_column(String(200))
    certificate_url: Mapped[str | None] = mapped_column(String(500))

    status: Mapped[DestructionStatus] = mapped_column(
        destruction_status_enum, nullable=False, default=DestructionStatus.scheduled
    )
    handler_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))
    verifier_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verification_note: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


# === Third-party ===
class ThirdPartyProcessor(Base):
    __tablename__ = "third_party_processors"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_name: Mapped[str] = mapped_column(String(200), nullable=False)
    business_number: Mapped[str | None] = mapped_column(String(20))
    contact_person: Mapped[str | None] = mapped_column(String(100))
    contact_email: Mapped[str | None] = mapped_column(String(255))
    contact_phone: Mapped[str | None] = mapped_column(String(50))

    purpose: Mapped[str] = mapped_column(Text, nullable=False)
    data_categories: Mapped[str] = mapped_column(Text, nullable=False)

    contract_start: Mapped[date] = mapped_column(Date, nullable=False)
    contract_end: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    is_sub_delegated: Mapped[bool] = mapped_column(Boolean, default=False)
    parent_processor_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("third_party_processors.id"))

    disclosure_channel: Mapped[str | None] = mapped_column(String(100))
    disclosure_url: Mapped[str | None] = mapped_column(String(500))
    disclosure_started_at: Mapped[date | None] = mapped_column(Date)
    is_marketing_delegation: Mapped[bool] = mapped_column(Boolean, default=False)
    contract_file_key: Mapped[str | None] = mapped_column(String(500))
    required_clauses_checked: Mapped[bool] = mapped_column(Boolean, default=False)

    security_audit_done: Mapped[bool] = mapped_column(Boolean, default=False)
    audit_date: Mapped[date | None] = mapped_column(Date)
    audit_result: Mapped[str | None] = mapped_column(Text)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


# === Incident ===
class IncidentSeverity(str, PyEnum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class IncidentStatus(str, PyEnum):
    detected = "detected"
    analyzing = "analyzing"
    containing = "containing"
    recovering = "recovering"
    resolved = "resolved"
    closed = "closed"


incident_severity_enum = ENUM(IncidentSeverity, name="incident_severity", create_type=False)
incident_status_enum = ENUM(IncidentStatus, name="incident_status", create_type=False)


class Incident(Base):
    __tablename__ = "incidents"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    severity: Mapped[IncidentSeverity] = mapped_column(incident_severity_enum, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)

    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    notification_deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    reportable_to_authority: Mapped[bool] = mapped_column(Boolean, default=False)
    report_threshold_basis: Mapped[str | None] = mapped_column(String(200))
    illegal_external_access: Mapped[bool] = mapped_column(Boolean, default=False)
    initial_report_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    supplemental_report_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    subjects_notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notification_exception_reason: Mapped[str | None] = mapped_column(Text)
    website_notice_posted_from: Mapped[date | None] = mapped_column(Date)
    website_notice_posted_to: Mapped[date | None] = mapped_column(Date)

    affected_subjects_count: Mapped[int | None] = mapped_column(Integer)
    data_types_affected: Mapped[str | None] = mapped_column(Text)
    includes_sensitive_data: Mapped[bool] = mapped_column(Boolean, default=False)
    root_cause: Mapped[str | None] = mapped_column(Text)
    remediation: Mapped[str | None] = mapped_column(Text)

    status: Mapped[IncidentStatus] = mapped_column(
        incident_status_enum, nullable=False, default=IncidentStatus.detected
    )
    handler_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class IncidentTimeline(Base):
    __tablename__ = "incident_timeline"

    id: Mapped[int] = mapped_column(primary_key=True)
    incident_id: Mapped[int] = mapped_column(Integer, ForeignKey("incidents.id", ondelete="CASCADE"))
    action: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    performed_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))
    performed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
