"""APScheduler deadline tracker — runs hourly, creates notifications + auto-overdue/expire."""

from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models.audit import AuditLog
from app.models.corrective import CorrectiveAction, CorrectiveStatus
from app.models.evidence import Evidence, EvidenceStatus
from app.models.notification import Notification
from app.models.pipa import DestructionRecord, DestructionStatus, DSRRequest, DSRStatus, Incident, ThirdPartyProcessor


async def _create_notification(
    db: AsyncSession, entity_type: str, entity_id: int, ntype: str, title: str, msg: str, user_id: int | None = None
):
    """Create notification only if not already exists (dedup)."""
    existing = (
        await db.execute(
            select(Notification).where(
                Notification.entity_type == entity_type,
                Notification.entity_id == entity_id,
                Notification.type == ntype,
            )
        )
    ).scalar_one_or_none()
    if not existing:
        db.add(
            Notification(
                user_id=user_id, type=ntype, title=title, message=msg, entity_type=entity_type, entity_id=entity_id
            )
        )


async def check_deadlines():
    """Main scheduler job — call every hour."""
    async with async_session() as db:
        today = date.today()
        now = datetime.now(UTC)

        # 1. DSR deadlines + auto-overdue
        dsrs = (
            await db.execute(select(DSRRequest).where(DSRRequest.status.in_(["received", "assigned", "processing"])))
        ).scalars()
        for dsr in dsrs:
            days_left = (dsr.due_date - today).days
            if days_left < 0:
                dsr.status = DSRStatus.overdue
                await _create_notification(
                    db, "dsr_request", dsr.id, "dsr_overdue", f"DSR #{dsr.id} 기한 초과", "처리 기한이 경과했습니다"
                )
            elif days_left <= 5:
                await _create_notification(
                    db,
                    "dsr_request",
                    dsr.id,
                    f"dsr_d{days_left}",
                    f"DSR #{dsr.id} D-{days_left}",
                    f"처리 기한 {days_left}일 남음",
                )

        # 2. Destruction deadlines + auto-overdue
        destructions = (
            await db.execute(
                select(DestructionRecord).where(DestructionRecord.status.in_(["scheduled", "in_progress"]))
            )
        ).scalars()
        for rec in destructions:
            days_left = (rec.scheduled_date - today).days
            if days_left < 0:
                rec.status = DestructionStatus.overdue
                await _create_notification(
                    db, "destruction_record", rec.id, "destruction_overdue", f"파기 #{rec.id} 기한 초과", ""
                )
            elif days_left <= 5:
                await _create_notification(
                    db, "destruction_record", rec.id, f"destruction_d{days_left}", f"파기 #{rec.id} D-{days_left}", ""
                )

        # 3. Incident 72h deadline
        incidents = (await db.execute(select(Incident).where(Incident.status.not_in(["resolved", "closed"])))).scalars()
        for inc in incidents:
            hours_left = (inc.notification_deadline - now).total_seconds() / 3600
            if hours_left <= 24 and hours_left > 0:
                await _create_notification(
                    db,
                    "incident",
                    inc.id,
                    f"incident_h{int(hours_left)}",
                    f"사고 #{inc.id} H-{int(hours_left)}",
                    "72시간 기한 임박",
                )

        # 4. Third-party contract expiry
        tps = (await db.execute(select(ThirdPartyProcessor).where(ThirdPartyProcessor.is_active == True))).scalars()
        for tp in tps:
            days_left = (tp.contract_end - today).days
            for threshold in [30, 14, 7]:
                if days_left == threshold:
                    await _create_notification(
                        db,
                        "third_party",
                        tp.id,
                        f"contract_d{threshold}",
                        f"위탁 '{tp.company_name}' D-{threshold}",
                        "계약 만료 임박",
                    )

        # 5. Evidence expire alert + auto-expire
        expiring = (
            await db.execute(
                select(Evidence).where(Evidence.status == EvidenceStatus.approved, Evidence.valid_to.isnot(None))
            )
        ).scalars()
        for ev in expiring:
            days_left = (ev.valid_to - today).days
            if days_left < 0:
                ev.status = EvidenceStatus.expired
                db.add(AuditLog(action="AUTO_EXPIRE", entity_type="evidence", entity_id=ev.id))
                await _create_notification(
                    db,
                    "evidence",
                    ev.id,
                    "evidence_expired",
                    f"증적 '{ev.title}' 만료",
                    "유효기간이 경과하여 자동 만료되었습니다",
                )
            elif days_left <= 30:
                await _create_notification(
                    db,
                    "evidence",
                    ev.id,
                    f"evidence_d{days_left}",
                    f"증적 '{ev.title}' D-{days_left}",
                    "유효기간 만료 임박",
                )

        # 6. Corrective action deadlines + auto-overdue
        cas = (
            await db.execute(select(CorrectiveAction).where(CorrectiveAction.status.in_(["open", "in_progress"])))
        ).scalars()
        for ca in cas:
            days_left = (ca.due_date - today).days
            if days_left < 0:
                ca.status = CorrectiveStatus.overdue
                await _create_notification(
                    db, "corrective_action", ca.id, "ca_overdue", f"시정조치 #{ca.id} 기한 초과", ""
                )
            elif days_left <= 14:
                await _create_notification(
                    db, "corrective_action", ca.id, f"ca_d{days_left}", f"시정조치 #{ca.id} D-{days_left}", ""
                )

        await db.commit()
