from datetime import date, datetime
from enum import Enum as PyEnum

from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import ENUM
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class EvidenceType(str, PyEnum):
    document = "document"
    prowler = "prowler"
    pipa_record = "pipa_record"
    external_link = "external_link"


class EvidenceStatus(str, PyEnum):
    draft = "draft"
    submitted = "submitted"
    approved = "approved"
    rejected = "rejected"
    expired = "expired"
    replaced = "replaced"


evidence_type_enum = ENUM(EvidenceType, name="evidence_type", create_type=False)
evidence_status_enum = ENUM(EvidenceStatus, name="evidence_status", create_type=False)


class Evidence(Base):
    __tablename__ = "evidence"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    evidence_type: Mapped[EvidenceType] = mapped_column(
        evidence_type_enum, nullable=False, default=EvidenceType.document
    )

    # document
    file_key: Mapped[str | None] = mapped_column(String(500))
    file_name: Mapped[str | None] = mapped_column(String(255))
    file_size: Mapped[int | None] = mapped_column(BigInteger)
    mime_type: Mapped[str | None] = mapped_column(String(100))
    file_hash: Mapped[str | None] = mapped_column(String(64))

    # external_link
    external_url: Mapped[str | None] = mapped_column(String(1000))

    # prowler
    scan_job_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("scan_jobs.id"))

    # pipa_record
    source_module: Mapped[str | None] = mapped_column(String(50))
    source_id: Mapped[int | None] = mapped_column(Integer)

    # common
    status: Mapped[EvidenceStatus] = mapped_column(evidence_status_enum, nullable=False, default=EvidenceStatus.draft)
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date, index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    parent_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("evidence.id"))

    uploaded_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))
    reviewed_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_comment: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (Index("idx_evidence_status", "status"),)


class EvidenceItemLink(Base):
    __tablename__ = "evidence_item_links"

    id: Mapped[int] = mapped_column(primary_key=True)
    evidence_id: Mapped[int] = mapped_column(Integer, ForeignKey("evidence.id", ondelete="CASCADE"))
    item_id: Mapped[int] = mapped_column(Integer, ForeignKey("isms_items.id", ondelete="CASCADE"))
    relevance_note: Mapped[str | None] = mapped_column(Text)
    linked_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))
    linked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint("evidence_id", "item_id"),)
