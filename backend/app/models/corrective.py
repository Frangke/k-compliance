from datetime import date, datetime
from enum import Enum as PyEnum

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import ENUM
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class CorrectiveSource(str, PyEnum):
    external_audit = "external_audit"
    internal_review = "internal_review"
    prowler = "prowler"
    config = "config"
    other = "other"


class CorrectiveStatus(str, PyEnum):
    open = "open"
    in_progress = "in_progress"
    completed = "completed"
    verified = "verified"
    overdue = "overdue"


corrective_source_enum = ENUM(CorrectiveSource, name="corrective_source", create_type=False)
corrective_status_enum = ENUM(CorrectiveStatus, name="corrective_status", create_type=False)


class CorrectiveAction(Base):
    __tablename__ = "corrective_actions"

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[CorrectiveSource] = mapped_column(corrective_source_enum, nullable=False)
    source_detail: Mapped[str | None] = mapped_column(String(300))

    isms_item_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("isms_items.id"))

    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    action_plan: Mapped[str | None] = mapped_column(Text)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)

    status: Mapped[CorrectiveStatus] = mapped_column(
        corrective_status_enum, nullable=False, default=CorrectiveStatus.open
    )
    assigned_to: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))
    result: Mapped[str | None] = mapped_column(Text)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    evidence_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("evidence.id"))

    verified_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verification_note: Mapped[str | None] = mapped_column(Text)

    created_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("idx_ca_status", "status"),
        Index("idx_ca_isms_item", "isms_item_id"),
        Index("idx_ca_due_date", "due_date"),
    )
