from datetime import UTC, date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user, require_role
from app.models.pipa import DSRRequest, DSRStatus
from app.models.user import User
from app.schemas.pipa import DSRCreate, DSRResponse, DSRUpdate
from app.services.audit import log_audit

router = APIRouter(prefix="/api/pipa/dsr", tags=["pipa-dsr"])

TERMINAL = {DSRStatus.completed, DSRStatus.rejected, DSRStatus.overdue}


def _calc_due_date(received_at: datetime) -> date:
    # KST date + 10 calendar days
    kst = received_at.astimezone(timezone(timedelta(hours=9)))
    return kst.date() + timedelta(days=10)


@router.get("", response_model=list[DSRResponse])
async def list_dsr(
    status: str | None = None,
    request_type: str | None = None,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    q = select(DSRRequest)
    if status:
        q = q.where(DSRRequest.status == status)
    if request_type:
        q = q.where(DSRRequest.request_type == request_type)
    result = await db.execute(q.order_by(DSRRequest.id.desc()).offset((page - 1) * size).limit(size))
    return result.scalars().all()


@router.post("", response_model=DSRResponse, status_code=201)
async def create_dsr(
    body: DSRCreate,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    now = datetime.now(UTC)
    dsr = DSRRequest(
        **body.model_dump(),
        received_at=now,
        due_date=_calc_due_date(now),
        created_by=current_user.id,
    )
    db.add(dsr)
    await db.flush()
    await log_audit(
        db,
        current_user.id,
        "create",
        "dsr_request",
        dsr.id,
        new_values={
            "request_type": dsr.request_type.value if hasattr(dsr.request_type, "value") else str(dsr.request_type),
            "requester_name": dsr.requester_name,
            "due_date": str(dsr.due_date),
        },
        request=request,
    )
    await db.commit()
    await db.refresh(dsr)
    return dsr


@router.put("/{dsr_id}", response_model=DSRResponse)
async def update_dsr(
    dsr_id: int,
    body: DSRUpdate,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    dsr = (await db.execute(select(DSRRequest).where(DSRRequest.id == dsr_id))).scalar_one_or_none()
    if not dsr:
        raise HTTPException(404, "DSR을 찾을 수 없습니다")
    changes = {}
    for field, value in body.model_dump(exclude_unset=True).items():
        if field == "due_date":
            continue  # read-only
        if field == "status" and value == "processing" and DSRStatus(dsr.status) not in TERMINAL:
            dsr.status = DSRStatus.processing
            changes["status"] = "processing"
        elif field != "status":
            setattr(dsr, field, value)
            changes[field] = value
    await log_audit(db, current_user.id, "update", "dsr_request", dsr.id, new_values=changes, request=request)
    await db.commit()
    await db.refresh(dsr)
    return dsr


@router.post("/{dsr_id}/assign")
async def assign_dsr(
    dsr_id: int,
    request: Request,
    assigned_to: int = Query(...),
    current_user: User = Depends(require_role(["cpo", "security_officer"])),
    db: AsyncSession = Depends(get_db),
):
    dsr = (await db.execute(select(DSRRequest).where(DSRRequest.id == dsr_id))).scalar_one_or_none()
    if not dsr:
        raise HTTPException(404, "DSR을 찾을 수 없습니다")
    if DSRStatus(dsr.status) in TERMINAL:
        raise HTTPException(400, "종료된 요청은 배정할 수 없습니다")
    dsr.assigned_to = assigned_to
    if DSRStatus(dsr.status) == DSRStatus.received:
        dsr.status = DSRStatus.assigned
    await log_audit(
        db, current_user.id, "assign", "dsr_request", dsr.id, new_values={"assigned_to": assigned_to}, request=request
    )
    await db.commit()
    return {"message": "담당자가 배정되었습니다"}


@router.post("/{dsr_id}/complete")
async def complete_dsr(
    dsr_id: int,
    request: Request,
    result_description: str = Query(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    dsr = (await db.execute(select(DSRRequest).where(DSRRequest.id == dsr_id))).scalar_one_or_none()
    if not dsr:
        raise HTTPException(404, "DSR을 찾을 수 없습니다")
    if DSRStatus(dsr.status) in TERMINAL:
        raise HTTPException(400, "이미 종료된 요청입니다")
    if not result_description.strip():
        raise HTTPException(400, "처리 결과를 입력해주세요")
    dsr.status = DSRStatus.completed
    dsr.result_description = result_description
    dsr.completed_at = datetime.now(UTC)

    # Separation of duties (soft): assignee == completer is allowed because in
    # small teams one person processes and reports. Tag the audit log so an
    # ISMS-P reviewer can still spot the case (tag regardless of role so CPO
    # self-operations are also traceable; warning only surfaces for non-CPO).
    audit_extra: dict = {}
    warning: str | None = None
    if dsr.assigned_to and dsr.assigned_to == current_user.id:
        audit_extra["self_complete"] = True
        if current_user.role != "cpo":
            warning = "처리 담당자와 완료 보고자가 동일합니다 (ISMS-P 2.5.1 권고: 분리)"

    await log_audit(
        db, current_user.id, "complete", "dsr_request", dsr.id, new_values=audit_extra or None, request=request
    )
    await db.commit()
    resp: dict = {"message": "DSR 처리가 완료되었습니다"}
    if warning:
        resp["warning"] = warning
    return resp


@router.post("/{dsr_id}/reject")
async def reject_dsr(
    dsr_id: int,
    request: Request,
    rejection_reason: str = Query(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    dsr = (await db.execute(select(DSRRequest).where(DSRRequest.id == dsr_id))).scalar_one_or_none()
    if not dsr:
        raise HTTPException(404, "DSR을 찾을 수 없습니다")
    if DSRStatus(dsr.status) in TERMINAL:
        raise HTTPException(400, "이미 종료된 요청입니다")
    if not rejection_reason.strip():
        raise HTTPException(400, "거부 사유를 입력해주세요")
    dsr.status = DSRStatus.rejected
    dsr.rejection_reason = rejection_reason
    dsr.completed_at = datetime.now(UTC)
    await log_audit(
        db,
        current_user.id,
        "reject",
        "dsr_request",
        dsr.id,
        new_values={"rejection_reason": rejection_reason},
        request=request,
    )
    await db.commit()
    return {"message": "DSR 요청이 거부되었습니다"}
