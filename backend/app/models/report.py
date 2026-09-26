"""Generated reports model."""

from datetime import date, datetime
from enum import Enum as PyEnum

from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import ENUM
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ReportType(str, PyEnum):
    isms_assessment = "isms_assessment"
    corrective_action = "corrective_action"
    evidence_summary = "evidence_summary"
    evidence_package = "evidence_package"
    dashboard_snapshot = "dashboard_snapshot"


class ReportStatus(str, PyEnum):
    generating = "generating"
    completed = "completed"
    failed = "failed"


report_type_enum = ENUM(ReportType, name="report_type", create_type=False)
report_status_enum = ENUM(ReportStatus, name="report_status", create_type=False)


class GeneratedReport(Base):
    __tablename__ = "generated_reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    report_code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    report_type: Mapped[ReportType] = mapped_column(report_type_enum, nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[ReportStatus] = mapped_column(report_status_enum, nullable=False, default=ReportStatus.generating)

    file_key: Mapped[str | None] = mapped_column(String(500))
    file_size: Mapped[int | None] = mapped_column(BigInteger)
    error_message: Mapped[str | None] = mapped_column(Text)

    # Optional link to an assessment round (P1-2). Existing reports keep NULL.
    assessment_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("assessments.id", ondelete="SET NULL"), index=True
    )

    generated_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (Index("idx_report_type_period", "report_type", "period_start", "period_end"),)
