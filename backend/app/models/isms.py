from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ISMSDomain(Base):
    __tablename__ = "isms_domains"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(10), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False)


class ISMSSubdomain(Base):
    __tablename__ = "isms_subdomains"

    id: Mapped[int] = mapped_column(primary_key=True)
    domain_id: Mapped[int] = mapped_column(Integer, ForeignKey("isms_domains.id"))
    code: Mapped[str] = mapped_column(String(10), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False)


class ISMSItem(Base):
    __tablename__ = "isms_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    subdomain_id: Mapped[int] = mapped_column(Integer, ForeignKey("isms_subdomains.id"))
    code: Mapped[str] = mapped_column(String(10), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    required_evidence: Mapped[str | None] = mapped_column(Text)
    has_prowler_checks: Mapped[bool] = mapped_column(Boolean, default=False)
    prowler_check_count: Mapped[int] = mapped_column(Integer, default=0)
    has_config_rules: Mapped[bool] = mapped_column(Boolean, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False)


class ISMSChecklist(Base):
    __tablename__ = "isms_checklists"

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(Integer, ForeignKey("isms_items.id"))
    question: Mapped[str] = mapped_column(Text, nullable=False)
    guidance: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False)


class ISMSItemAssignment(Base):
    __tablename__ = "isms_item_assignments"

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(Integer, ForeignKey("isms_items.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role_in_item: Mapped[str] = mapped_column(String(50), default="owner")
    assigned_by: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"))
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint("item_id", "user_id", "role_in_item"),)
