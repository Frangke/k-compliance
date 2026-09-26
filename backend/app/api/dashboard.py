"""Dashboard aggregation APIs — SPEC 4.8 (8 endpoints)."""

from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.aws_config import ConfigEvaluation, ConfigSyncJob
from app.models.compliance import ComplianceSnapshot
from app.models.corrective import CorrectiveAction
from app.models.evidence import Evidence, EvidenceItemLink, EvidenceStatus
from app.models.isms import ISMSDomain, ISMSItem, ISMSItemAssignment, ISMSSubdomain
from app.models.pipa import DestructionRecord, DSRRequest, Incident, ThirdPartyProcessor
from app.models.prowler import FindingStatus, ProwlerFinding, RemediationStatus, ScanJob, ScanStatus
from app.models.user import User

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


# --- 1. Overview ---
@router.get("/overview")
async def overview(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    today = date.today()
    total_items = (await db.execute(select(func.count()).select_from(ISMSItem))).scalar()

    # Compliance rate (latest snapshot per item — continuous model)
    latest_ids = select(func.max(ComplianceSnapshot.id)).group_by(ComplianceSnapshot.item_id)
    compliant = (
        await db.execute(
            select(func.count())
            .select_from(ComplianceSnapshot)
            .where(ComplianceSnapshot.id.in_(latest_ids), ComplianceSnapshot.status == "compliant")
        )
    ).scalar()
    compliance_rate = round(compliant / total_items * 100, 1) if total_items > 0 else 0

    # Evidence status
    ev_approved = (
        await db.execute(
            select(func.count())
            .select_from(Evidence)
            .where(
                Evidence.status == EvidenceStatus.approved, or_(Evidence.valid_to.is_(None), Evidence.valid_to >= today)
            )
        )
    ).scalar()
    ev_expired = (
        await db.execute(select(func.count()).select_from(Evidence).where(Evidence.status == EvidenceStatus.expired))
    ).scalar()
    ev_expiring = (
        await db.execute(
            select(func.count())
            .select_from(Evidence)
            .where(
                Evidence.status == EvidenceStatus.approved,
                Evidence.valid_to.isnot(None),
                Evidence.valid_to.between(today, today + timedelta(days=30)),
            )
        )
    ).scalar()
    ev_submitted = (
        await db.execute(select(func.count()).select_from(Evidence).where(Evidence.status == EvidenceStatus.submitted))
    ).scalar()

    # Corrective actions
    ca_open = (
        await db.execute(
            select(func.count())
            .select_from(CorrectiveAction)
            .where(CorrectiveAction.status.in_(["open", "in_progress"]))
        )
    ).scalar()
    ca_overdue = (
        await db.execute(select(func.count()).select_from(CorrectiveAction).where(CorrectiveAction.status == "overdue"))
    ).scalar()

    # Urgent: DSR D-5 이내 + 사고 진행 중 + 시정조치 overdue
    dsr_urgent = (
        await db.execute(
            select(func.count())
            .select_from(DSRRequest)
            .where(
                DSRRequest.status.in_(["received", "assigned", "processing"]),
                DSRRequest.due_date <= today + timedelta(days=5),
            )
        )
    ).scalar()
    incidents_active = (
        await db.execute(
            select(func.count()).select_from(Incident).where(Incident.status.not_in(["resolved", "closed"]))
        )
    ).scalar()

    return {
        "total_items": total_items,
        "compliance_rate": compliance_rate,
        "compliant_count": compliant,
        "evidence": {
            "approved": ev_approved,
            "expired": ev_expired,
            "expiring_soon": ev_expiring,
            "pending_review": ev_submitted,
        },
        "corrective_actions": {"open": ca_open, "overdue": ca_overdue},
        "urgent": {"dsr_due_soon": dsr_urgent, "active_incidents": incidents_active, "ca_overdue": ca_overdue},
    }


# --- 2. Compliance trend ---
@router.get("/compliance-trend")
async def compliance_trend(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Group compliance snapshots by month (YYYY-MM) for trend analysis."""
    month_expr = func.to_char(ComplianceSnapshot.assessed_at, "YYYY-MM")
    result = await db.execute(
        select(
            month_expr.label("month"),
            ISMSDomain.code.label("domain_code"),
            func.count().label("total"),
            func.count().filter(ComplianceSnapshot.status == "compliant").label("compliant"),
        )
        .join(ISMSItem, ISMSItem.id == ComplianceSnapshot.item_id)
        .join(ISMSSubdomain, ISMSSubdomain.id == ISMSItem.subdomain_id)
        .join(ISMSDomain, ISMSDomain.id == ISMSSubdomain.domain_id)
        .group_by(month_expr, ISMSDomain.code)
        .order_by(month_expr, ISMSDomain.code)
    )
    return [
        {"period": r.month, "domain_code": r.domain_code, "total": r.total, "compliant": r.compliant}
        for r in result.all()
    ]


# --- 3. Evidence status ---
@router.get("/evidence-status")
async def evidence_status(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Evidence.status, func.count()).group_by(Evidence.status))
    return dict(result.all())


# --- 4. PIPA deadlines ---
@router.get("/pipa-deadlines")
async def pipa_deadlines(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    today = date.today()
    items = []

    # DSR
    dsrs = (
        await db.execute(
            select(DSRRequest)
            .where(DSRRequest.status.in_(["received", "assigned", "processing"]))
            .order_by(DSRRequest.due_date)
        )
    ).scalars()
    for d in dsrs:
        days = (d.due_date - today).days
        items.append(
            {
                "type": "dsr",
                "id": d.id,
                "title": f"DSR #{d.id} ({d.requester_name})",
                "due_date": str(d.due_date),
                "d_day": days,
            }
        )

    # Destruction
    dests = (
        await db.execute(
            select(DestructionRecord)
            .where(DestructionRecord.status.in_(["scheduled", "in_progress"]))
            .order_by(DestructionRecord.scheduled_date)
        )
    ).scalars()
    for d in dests:
        days = (d.scheduled_date - today).days
        items.append(
            {
                "type": "destruction",
                "id": d.id,
                "title": f"파기 #{d.id} ({d.data_category})",
                "due_date": str(d.scheduled_date),
                "d_day": days,
            }
        )

    # Third-party contract expiry
    tps = (
        await db.execute(
            select(ThirdPartyProcessor).where(
                ThirdPartyProcessor.is_active == True, ThirdPartyProcessor.contract_end <= today + timedelta(days=30)
            )
        )
    ).scalars()
    for tp in tps:
        days = (tp.contract_end - today).days
        items.append(
            {
                "type": "contract",
                "id": tp.id,
                "title": f"위탁 '{tp.company_name}'",
                "due_date": str(tp.contract_end),
                "d_day": days,
            }
        )

    # Incidents with deadline approaching
    incs = (await db.execute(select(Incident).where(Incident.status.not_in(["resolved", "closed"])))).scalars()
    now = datetime.now(UTC)
    for inc in incs:
        hours = (inc.notification_deadline - now).total_seconds() / 3600
        items.append(
            {"type": "incident", "id": inc.id, "title": f"사고 #{inc.id} ({inc.title})", "hours_left": round(hours, 1)}
        )

    # Corrective actions
    cas = (
        await db.execute(
            select(CorrectiveAction)
            .where(CorrectiveAction.status.in_(["open", "in_progress"]))
            .order_by(CorrectiveAction.due_date)
        )
    ).scalars()
    for ca in cas:
        days = (ca.due_date - today).days
        items.append(
            {
                "type": "corrective",
                "id": ca.id,
                "title": f"시정조치 #{ca.id} ({ca.title})",
                "due_date": str(ca.due_date),
                "d_day": days,
            }
        )

    items.sort(key=lambda x: x.get("d_day", x.get("hours_left", 999)))
    return items


# --- 5. Prowler summary ---
@router.get("/prowler-summary")
async def prowler_summary(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    latest = (
        await db.execute(select(ScanJob).where(ScanJob.status == ScanStatus.completed).order_by(ScanJob.id.desc()))
    ).scalar_one_or_none()
    if not latest:
        return {"message": "스캔 기록 없음", "passed": 0, "failed": 0, "total": 0, "remediation_pending": 0}

    pending = (
        await db.execute(
            select(func.count())
            .select_from(ProwlerFinding)
            .where(
                ProwlerFinding.scan_job_id == latest.id,
                ProwlerFinding.status == FindingStatus.FAIL,
                ProwlerFinding.remediation_status == RemediationStatus.open,
            )
        )
    ).scalar()

    return {
        "scan_id": latest.id,
        "passed": latest.passed,
        "failed": latest.failed,
        "total": latest.total_checks,
        "remediation_pending": pending,
        "scanned_at": latest.completed_at.isoformat() if latest.completed_at else None,
    }


# --- 6. Config summary ---
@router.get("/config-summary")
async def config_summary(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    latest = (
        await db.execute(
            select(ConfigSyncJob).where(ConfigSyncJob.status == ScanStatus.completed).order_by(ConfigSyncJob.id.desc())
        )
    ).scalar_one_or_none()
    if not latest:
        return {
            "message": "동기화 기록 없음",
            "compliant": 0,
            "non_compliant": 0,
            "total_rules": 0,
            "remediation_pending": 0,
        }

    pending = (
        await db.execute(
            select(func.count())
            .select_from(ConfigEvaluation)
            .where(
                ConfigEvaluation.sync_job_id == latest.id,
                ConfigEvaluation.compliance_type == "NON_COMPLIANT",
                ConfigEvaluation.remediation_status == RemediationStatus.open,
            )
        )
    ).scalar()

    return {
        "sync_job_id": latest.id,
        "compliant": latest.compliant,
        "non_compliant": latest.non_compliant,
        "total_rules": latest.total_rules,
        "remediation_pending": pending,
        "synced_at": latest.completed_at.isoformat() if latest.completed_at else None,
    }


# --- 7. Automated coverage ---
@router.get("/automated-coverage")
async def automated_coverage(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    prowler_items = (
        await db.execute(select(func.count()).select_from(ISMSItem).where(ISMSItem.has_prowler_checks == True))
    ).scalar()
    config_items = (
        await db.execute(select(func.count()).select_from(ISMSItem).where(ISMSItem.has_config_rules == True))
    ).scalar()
    both = (
        await db.execute(
            select(func.count())
            .select_from(ISMSItem)
            .where(ISMSItem.has_prowler_checks == True, ISMSItem.has_config_rules == True)
        )
    ).scalar()
    total = (await db.execute(select(func.count()).select_from(ISMSItem))).scalar()
    covered = prowler_items + config_items - both  # union

    return {
        "total_items": total,
        "prowler_items": prowler_items,
        "config_items": config_items,
        "both": both,
        "covered": covered,
        "coverage_rate": round(covered / total * 100, 1) if total > 0 else 0,
    }


# --- 8. My assignments ---
@router.get("/my-assignments")
async def my_assignments(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    # Assigned items with details
    assigned_result = await db.execute(
        select(ISMSItemAssignment.item_id, ISMSItemAssignment.role_in_item, ISMSItem.code, ISMSItem.name)
        .join(ISMSItem, ISMSItemAssignment.item_id == ISMSItem.id)
        .where(ISMSItemAssignment.user_id == current_user.id)
        .order_by(ISMSItem.code)
    )
    assigned_rows = assigned_result.all()
    assigned_items = len(assigned_rows)
    assigned_items_detail = [
        {"item_id": r.item_id, "code": r.code, "name": r.name, "role": r.role_in_item} for r in assigned_rows
    ]

    # Items with missing evidence (assigned to me, 0 approved evidence)
    items_no_evidence = 0
    missing_evidence_items = []
    for r in assigned_rows:
        approved = (
            await db.execute(
                select(func.count())
                .select_from(EvidenceItemLink)
                .join(Evidence)
                .where(EvidenceItemLink.item_id == r.item_id, Evidence.status == EvidenceStatus.approved)
            )
        ).scalar()
        if approved == 0:
            items_no_evidence += 1
            missing_evidence_items.append({"code": r.code, "name": r.name})

    # Pending review (for CPO/security_officer)
    pending_review = 0
    if current_user.role in ("cpo", "security_officer"):
        pending_review = (
            await db.execute(
                select(func.count()).select_from(Evidence).where(Evidence.status == EvidenceStatus.submitted)
            )
        ).scalar()

    # Assigned DSRs
    my_dsrs = (
        await db.execute(
            select(func.count())
            .select_from(DSRRequest)
            .where(DSRRequest.assigned_to == current_user.id, DSRRequest.status.in_(["assigned", "processing"]))
        )
    ).scalar()

    # Assigned corrective actions
    my_cas = (
        await db.execute(
            select(func.count())
            .select_from(CorrectiveAction)
            .where(
                CorrectiveAction.assigned_to == current_user.id, CorrectiveAction.status.in_(["open", "in_progress"])
            )
        )
    ).scalar()

    return {
        "assigned_items": assigned_items,
        "assigned_items_detail": assigned_items_detail,
        "items_missing_evidence": items_no_evidence,
        "missing_evidence_items": missing_evidence_items,
        "pending_review": pending_review,
        "assigned_dsrs": my_dsrs,
        "assigned_corrective_actions": my_cas,
    }
