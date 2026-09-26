from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user, require_role
from app.models.pipa import DestructionRecord, DestructionStatus
from app.models.user import User
from app.schemas.pipa import DestructionCreate, DestructionExecute, DestructionResponse, DestructionVerify
from app.services.audit import log_audit

router = APIRouter(prefix="/api/pipa/destruction", tags=["pipa-destruction"])


@router.get("", response_model=list[DestructionResponse])
async def list_destruction(
    status: str | None = None, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    q = select(DestructionRecord)
    if status:
        q = q.where(DestructionRecord.status == status)
    return (await db.execute(q.order_by(DestructionRecord.id.desc()))).scalars().all()


@router.post("", response_model=DestructionResponse, status_code=201)
async def create_destruction(
    body: DestructionCreate,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if body.scheduled_date < body.retention_expiry:
        raise HTTPException(400, "파기 예정일은 보유기간 만료일 이후여야 합니다")
    rec = DestructionRecord(**body.model_dump())
    db.add(rec)
    await db.flush()
    await log_audit(
        db,
        current_user.id,
        "create",
        "destruction_record",
        rec.id,
        new_values={
            "data_category": rec.data_category,
            "retention_expiry": str(rec.retention_expiry),
            "scheduled_date": str(rec.scheduled_date),
        },
        request=request,
    )
    await db.commit()
    await db.refresh(rec)
    return rec


@router.post("/{rec_id}/execute")
async def execute_destruction(
    rec_id: int,
    body: DestructionExecute,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    rec = (await db.execute(select(DestructionRecord).where(DestructionRecord.id == rec_id))).scalar_one_or_none()
    if not rec:
        raise HTTPException(404, "파기 기록을 찾을 수 없습니다")
    rec.method = body.method
    rec.actual_date = body.actual_date
    rec.handler_id = current_user.id
    rec.status = DestructionStatus.completed
    await log_audit(
        db,
        current_user.id,
        "execute",
        "destruction_record",
        rec_id,
        new_values={"method": body.method, "actual_date": str(body.actual_date)},
        request=request,
    )
    await db.commit()
    return {"message": "파기 실행이 기록되었습니다"}


@router.post("/{rec_id}/verify")
async def verify_destruction(
    rec_id: int,
    body: DestructionVerify,
    request: Request,
    current_user: User = Depends(require_role(["cpo", "security_officer"])),
    db: AsyncSession = Depends(get_db),
):
    rec = (await db.execute(select(DestructionRecord).where(DestructionRecord.id == rec_id))).scalar_one_or_none()
    if not rec:
        raise HTTPException(404, "파기 기록을 찾을 수 없습니다")
    if DestructionStatus(rec.status) != DestructionStatus.completed:
        raise HTTPException(400, "파기 실행이 완료된 후에만 검증할 수 있습니다")
    if rec.handler_id == current_user.id and current_user.role != "cpo":
        raise HTTPException(400, "파기 실행자는 직접 검증할 수 없습니다")

    rec.verifier_id = current_user.id
    rec.verified_at = datetime.now(UTC)
    rec.verification_note = body.verification_note
    rec.certificate_url = body.certificate_url
    rec.status = DestructionStatus.verified

    audit_extra = {"self_verify": True} if rec.handler_id == current_user.id else {}
    await log_audit(
        db,
        current_user.id,
        "verify",
        "destruction_record",
        rec_id,
        new_values={"status": "verified", **audit_extra},
        request=request,
    )
    await db.commit()
    return {"message": "파기 검증이 완료되었습니다"}
