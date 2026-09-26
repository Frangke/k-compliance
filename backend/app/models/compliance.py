from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import ENUM
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ComplianceLevel(str, PyEnum):
    compliant = "compliant"
    partial = "partial"
    non_compliant = "non_compliant"
    not_applicable = "not_applicable"


compliance_level_enum = ENUM(ComplianceLevel, name="compliance_level", create_type=False)


class ComplianceSnapshot(Base):
    __tablename__ = "compliance_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(Integer, ForeignKey("isms_items.id"))
    # Optional — NULL = legacy/global flow, non-NULL = scoped to a specific
    # audit round so the same item can be assessed twice independently.
    assessment_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("assessments.id", ondelete="SET NULL"), index=True
    )
    status: Mapped[ComplianceLevel] = mapped_column(compliance_level_enum, nullable=False)

    prowler_passed: Mapped[int] = mapped_column(Integer, default=0)
    prowler_failed: Mapped[int] = mapped_column(Integer, default=0)
    prowler_total: Mapped[int] = mapped_column(Integer, default=0)

    config_compliant: Mapped[int] = mapped_column(Integer, default=0)
    config_non_compliant: Mapped[int] = mapped_column(Integer, default=0)
    config_total: Mapped[int] = mapped_column(Integer, default=0)

    checklist_checked: Mapped[int] = mapped_column(Integer, default=0)
    checklist_total: Mapped[int] = mapped_column(Integer, default=0)

    evidence_count: Mapped[int] = mapped_column(Integer, default=0)
    evidence_approved: Mapped[int] = mapped_column(Integer, default=0)

    # Snapshot of checklist states at assessment time
    checklist_snapshot: Mapped[list | None] = mapped_column(JSON, nullable=True)

    notes: Mapped[str | None] = mapped_column(Text)
    assessed_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))
    assessed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ChecklistResponse(Base):
    __tablename__ = "checklist_responses"

    id: Mapped[int] = mapped_column(primary_key=True)
    checklist_id: Mapped[int] = mapped_column(Integer, ForeignKey("isms_checklists.id"))
    is_checked: Mapped[bool] = mapped_column(Boolean, default=False)
    evidence_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("evidence.id"))
    notes: Mapped[str | None] = mapped_column(Text)
    checked_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))
    checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (UniqueConstraint("checklist_id"),)
