from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user, require_role
from app.models.pipa import Incident, IncidentTimeline
from app.models.user import User
from app.schemas.pipa import IncidentCreate, IncidentResponse, NotifySubjectsIn, ReportAuthorityIn, TimelineCreate
from app.services.audit import log_audit

router = APIRouter(prefix="/api/pipa/incidents", tags=["pipa-incident"])


@router.get("", response_model=list[IncidentResponse])
async def list_incidents(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return (await db.execute(select(Incident).order_by(Incident.id.desc()))).scalars().all()


@router.post("", response_model=IncidentResponse, status_code=201)
async def create_incident(
    body: IncidentCreate,
    request: Request,
    current_user: User = Depends(require_role(["cpo", "security_officer"])),
    db: AsyncSession = Depends(get_db),
):
    if body.detected_at > datetime.now(UTC):
        raise HTTPException(400, "탐지 시각은 현재 이전이어야 합니다")

    inc = Incident(
        **body.model_dump(),
        notification_deadline=body.detected_at + timedelta(hours=72),
        handler_id=current_user.id,
    )
    db.add(inc)
    await db.flush()
    await log_audit(
        db,
        current_user.id,
        "create",
        "incident",
        inc.id,
        new_values={
            "title": inc.title,
            "severity": inc.severity.value if hasattr(inc.severity, "value") else str(inc.severity),
            "detected_at": inc.detected_at.isoformat() if inc.detected_at else None,
            "notification_deadline": inc.notification_deadline.isoformat() if inc.notification_deadline else None,
        },
        request=request,
    )
    await db.commit()
    await db.refresh(inc)

    # Auto-suggest
    suggestions = []
    if (body.affected_subjects_count or 0) >= 1000:
        suggestions.append("1천명 이상")
    if body.includes_sensitive_data:
        suggestions.append("민감정보 포함")
    if body.illegal_external_access:
        suggestions.append("외부 불법접근")

    resp = IncidentResponse.model_validate(inc).model_dump()
    if suggestions:
        resp["suggestion"] = f"법정 신고 대상에 해당할 수 있습니다 (사유: {', '.join(suggestions)})"
    return resp


@router.put("/{inc_id}", response_model=IncidentResponse)
async def update_incident(
    inc_id: int,
    body: IncidentCreate,
    request: Request,
    current_user: User = Depends(require_role(["cpo", "security_officer"])),
    db: AsyncSession = Depends(get_db),
):
    inc = (await db.execute(select(Incident).where(Incident.id == inc_id))).scalar_one_or_none()
    if not inc:
        raise HTTPException(404, "사고를 찾을 수 없습니다")
    changes = body.model_dump()
    for field, value in changes.items():
        setattr(inc, field, value)
    await log_audit(db, current_user.id, "update", "incident", inc.id, new_values=changes, request=request)
    await db.commit()
    await db.refresh(inc)
    return inc


@router.post("/{inc_id}/timeline")
async def add_timeline(
    inc_id: int,
    body: TimelineCreate,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    inc = (await db.execute(select(Incident).where(Incident.id == inc_id))).scalar_one_or_none()
    if not inc:
        raise HTTPException(404, "사고를 찾을 수 없습니다")
    db.add(
        IncidentTimeline(
            incident_id=inc_id, action=body.action, description=body.description, performed_by=current_user.id
        )
    )
    await log_audit(
        db,
        current_user.id,
        "create",
        "incident_timeline",
        inc_id,
        new_values={"action": body.action, "description": body.description[:200] if body.description else None},
        request=request,
    )
    await db.commit()
    return {"message": "타임라인이 기록되었습니다"}


@router.post("/{inc_id}/report-authority")
async def report_authority(
    inc_id: int,
    body: ReportAuthorityIn,
    request: Request,
    current_user: User = Depends(require_role(["cpo", "security_officer"])),
    db: AsyncSession = Depends(get_db),
):
    inc = (await db.execute(select(Incident).where(Incident.id == inc_id))).scalar_one_or_none()
    if not inc:
        raise HTTPException(404, "사고를 찾을 수 없습니다")
    now = datetime.now(UTC)

    # Separation of duties. Initial report is hard-blocked if the incident
    # handler tries to file it — this is the moment most prone to cover-up
    # pressure. Supplemental reports only emit a warning (the handler usually
    # has the detailed follow-up context).
    audit_extra: dict = {}
    warning: str | None = None
    if inc.handler_id and inc.handler_id == current_user.id:
        if body.type == "initial":
            if current_user.role != "cpo":
                raise HTTPException(400, "사고 담당자는 최초 신고를 직접 기록할 수 없습니다 (직무분리)")
            audit_extra["self_report"] = True
        else:  # supplemental
            audit_extra["self_report"] = True
            warning = "사고 담당자와 보완 신고자가 동일합니다 (ISMS-P 2.5.1 권고: 분리)"

    if body.type == "initial":
        inc.initial_report_at = now
        inc.reportable_to_authority = True
    elif body.type == "supplemental":
        inc.supplemental_report_at = now
    else:
        raise HTTPException(400, "type은 'initial' 또는 'supplemental'이어야 합니다")

    await log_audit(
        db,
        current_user.id,
        "report.authority",
        "incident",
        inc_id,
        new_values={"report_type": body.type, "at": now.isoformat(), **audit_extra},
        request=request,
    )
    await db.commit()
    resp: dict = {"message": f"{'최초' if body.type == 'initial' else '보완'} 신고가 기록되었습니다"}
    if warning:
        resp["warning"] = warning
    return resp


@router.post("/{inc_id}/notify-subjects")
async def notify_subjects(
    inc_id: int,
    body: NotifySubjectsIn,
    request: Request,
    current_user: User = Depends(require_role(["cpo", "security_officer"])),
    db: AsyncSession = Depends(get_db),
):
    inc = (await db.execute(select(Incident).where(Incident.id == inc_id))).scalar_one_or_none()
    if not inc:
        raise HTTPException(404, "사고를 찾을 수 없습니다")
    notified = bool(body.notified_at)
    if body.notified_at:
        inc.subjects_notified_at = body.notified_at
    if body.exception_reason:
        inc.notification_exception_reason = body.exception_reason
    if body.website_notice_from:
        inc.website_notice_posted_from = body.website_notice_from
        inc.website_notice_posted_to = body.website_notice_to

    # Separation of duties (soft): handler logging the notification themselves
    # is allowed (small-team reality) but tagged for auditor visibility. Tag
    # regardless of role; warning only surfaces for non-CPO.
    audit_extra: dict = {}
    warning: str | None = None
    if inc.handler_id and inc.handler_id == current_user.id:
        audit_extra["self_notify"] = True
        if current_user.role != "cpo":
            warning = "사고 담당자와 통지 기록자가 동일합니다 (ISMS-P 2.5.1 권고: 분리)"

    await log_audit(
        db,
        current_user.id,
        "notify.subjects",
        "incident",
        inc_id,
        new_values={
            "notified": notified,
            "exception_reason": body.exception_reason,
            "website_notice": bool(body.website_notice_from),
            **audit_extra,
        },
        request=request,
    )
    await db.commit()
    resp: dict = {"message": "정보주체 통지가 기록되었습니다"}
    if warning:
        resp["warning"] = warning
    return resp
