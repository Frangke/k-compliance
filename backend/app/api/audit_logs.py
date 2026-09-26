import csv
import io
from datetime import date

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_role
from app.models.audit import AuditLog
from app.models.user import User

router = APIRouter(prefix="/api/audit-logs", tags=["audit"])

_audit_readers = require_role(["cpo", "security_officer", "auditor"])


def _build_query(
    entity_type: str | None,
    entity_id: int | None,
    user_id: int | None,
    action: str | None,
    date_from: date | None,
    date_to: date | None,
    search: str | None,
):
    q = select(AuditLog, User.username, User.name).outerjoin(User, User.id == AuditLog.user_id)
    count_q = select(func.count()).select_from(AuditLog)

    if entity_type:
        q = q.where(AuditLog.entity_type == entity_type)
        count_q = count_q.where(AuditLog.entity_type == entity_type)
    if entity_id:
        q = q.where(AuditLog.entity_id == entity_id)
        count_q = count_q.where(AuditLog.entity_id == entity_id)
    if user_id:
        q = q.where(AuditLog.user_id == user_id)
        count_q = count_q.where(AuditLog.user_id == user_id)
    if action:
        q = q.where(AuditLog.action.ilike(f"%{action}%"))
        count_q = count_q.where(AuditLog.action.ilike(f"%{action}%"))
    if date_from:
        q = q.where(func.date(AuditLog.created_at) >= date_from)
        count_q = count_q.where(func.date(AuditLog.created_at) >= date_from)
    if date_to:
        q = q.where(func.date(AuditLog.created_at) <= date_to)
        count_q = count_q.where(func.date(AuditLog.created_at) <= date_to)
    if search:
        s = f"%{search}%"
        q = q.where(
            AuditLog.action.ilike(s)
            | AuditLog.entity_type.ilike(s)
            | func.cast(AuditLog.entity_id, func.text()).ilike(s)
        )
        count_q = count_q.where(AuditLog.action.ilike(s) | AuditLog.entity_type.ilike(s))
    return q, count_q


@router.get("")
async def list_audit_logs(
    entity_type: str | None = None,
    entity_id: int | None = None,
    user_id: int | None = None,
    action: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    search: str | None = None,
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    current_user: User = Depends(_audit_readers),
    db: AsyncSession = Depends(get_db),
):
    q, count_q = _build_query(entity_type, entity_id, user_id, action, date_from, date_to, search)
    total = (await db.execute(count_q)).scalar()
    result = await db.execute(q.order_by(AuditLog.created_at.desc()).offset((page - 1) * size).limit(size))
    rows = result.all()

    return {
        "items": [
            {
                "id": log.id,
                "user_id": log.user_id,
                "username": username,
                "user_name": user_name,
                "action": log.action,
                "entity_type": log.entity_type,
                "entity_id": log.entity_id,
                "old_values": log.old_values,
                "new_values": log.new_values,
                "ip_address": log.ip_address,
                "user_agent": log.user_agent,
                "created_at": log.created_at.isoformat() if log.created_at else None,
            }
            for log, username, user_name in rows
        ],
        "total": total,
    }


@router.get("/entity-types")
async def list_entity_types(
    current_user: User = Depends(_audit_readers),
    db: AsyncSession = Depends(get_db),
):
    """Distinct entity_type values for filter dropdown."""
    result = await db.execute(
        select(AuditLog.entity_type, func.count()).group_by(AuditLog.entity_type).order_by(AuditLog.entity_type)
    )
    return [{"entity_type": et, "count": c} for et, c in result.all()]


@router.get("/actions")
async def list_actions(
    current_user: User = Depends(_audit_readers),
    db: AsyncSession = Depends(get_db),
):
    """Distinct action values for filter dropdown."""
    result = await db.execute(
        select(AuditLog.action, func.count()).group_by(AuditLog.action).order_by(func.count().desc())
    )
    return [{"action": a, "count": c} for a, c in result.all()]


@router.get("/export.csv")
async def export_audit_logs_csv(
    entity_type: str | None = None,
    entity_id: int | None = None,
    user_id: int | None = None,
    action: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    search: str | None = None,
    current_user: User = Depends(_audit_readers),
    db: AsyncSession = Depends(get_db),
):
    """Export filtered audit logs as CSV (UTF-8 BOM for Excel)."""
    q, _ = _build_query(entity_type, entity_id, user_id, action, date_from, date_to, search)
    q = q.order_by(AuditLog.created_at.desc()).limit(10000)
    rows = (await db.execute(q)).all()

    buf = io.StringIO()
    buf.write("\ufeff")
    writer = csv.writer(buf)
    writer.writerow(
        [
            "ID",
            "일시(UTC)",
            "사용자ID",
            "아이디",
            "이름",
            "액션",
            "엔티티타입",
            "엔티티ID",
            "IP",
            "User-Agent",
            "이전값(JSON)",
            "신규값(JSON)",
        ]
    )
    for log, username, user_name in rows:
        writer.writerow(
            [
                log.id,
                log.created_at.isoformat() if log.created_at else "",
                log.user_id or "",
                username or "",
                user_name or "",
                log.action,
                log.entity_type or "",
                log.entity_id or "",
                log.ip_address or "",
                (log.user_agent or "")[:200],
                str(log.old_values) if log.old_values else "",
                str(log.new_values) if log.new_values else "",
            ]
        )

    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="audit_logs.csv"'},
    )
