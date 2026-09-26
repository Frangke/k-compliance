"""Assessment entity — groups snapshots + reports under one audit session.

ISMS-P audit rounds come in three flavors that behave differently:
- initial: full 101-item evaluation, the very first certification
- surveillance: yearly post-cert check, typically a sampled subset
- renewal: every three years, full scope like initial but with prior history

We record these via `audit_type`, link sub-rounds back to their parent
round via `parent_assessment_id`, and control whether every item is
in-scope (`scope_mode=all_items`) or only a curated sample
(`scope_mode=subset` with rows in `assessment_scope_items`).

Existing snapshots/reports can still live without an assessment_id — the
"상시 평가" flow is unchanged.
"""

from datetime import date, datetime
from enum import Enum as PyEnum

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import ENUM
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AssessmentStatus(str, PyEnum):
    draft = "draft"
    active = "active"
    closed = "closed"


class AuditType(str, PyEnum):
    initial = "initial"  # 최초 심사
    surveillance = "surveillance"  # 사후 심사 (매년)
    renewal = "renewal"  # 갱신 심사 (3년)


class ScopeMode(str, PyEnum):
    all_items = "all_items"  # 전체 101개 항목
    subset = "subset"  # 샘플링 (사후심사 전형)


assessment_status_enum = ENUM(AssessmentStatus, name="assessment_status", create_type=False)
audit_type_enum = ENUM(AuditType, name="audit_type", create_type=False)
scope_mode_enum = ENUM(ScopeMode, name="scope_mode", create_type=False)


class Assessment(Base):
    __tablename__ = "assessments"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    framework: Mapped[str] = mapped_column(String(50), nullable=False, default="kisa_isms_p_2023")
    audit_type: Mapped[AuditType] = mapped_column(audit_type_enum, nullable=False, default=AuditType.initial)
    # Surveillance/renewal rounds point back to the initial (or renewal) round
    # they extend, so reports can pull prior history in.
    parent_assessment_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("assessments.id", ondelete="SET NULL"), index=True
    )
    scope_mode: Mapped[ScopeMode] = mapped_column(scope_mode_enum, nullable=False, default=ScopeMode.all_items)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    scope_note: Mapped[str | None] = mapped_column(Text)
    status: Mapped[AssessmentStatus] = mapped_column(
        assessment_status_enum, nullable=False, default=AssessmentStatus.draft
    )
    created_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("idx_assessment_period", "period_start", "period_end"),
        Index("idx_assessment_status", "status"),
    )


class AssessmentScopeItem(Base):
    """Which ISMS-P items belong to a given assessment round."""

    __tablename__ = "assessment_scope_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    assessment_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("assessments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    item_id: Mapped[int] = mapped_column(Integer, ForeignKey("isms_items.id", ondelete="CASCADE"), nullable=False)
    # True when this row is a deliberate sample for a surveillance audit.
    # For all_items scope this is always False.
    is_sample: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    __table_args__ = (UniqueConstraint("assessment_id", "item_id", name="uq_scope_item"),)
