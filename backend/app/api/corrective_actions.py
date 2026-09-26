from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user, require_role
from app.models.corrective import CorrectiveAction, CorrectiveStatus
from app.models.user import User
from app.schemas.pipa import CorrectiveComplete, CorrectiveCreate, CorrectiveResponse, CorrectiveVerify
from app.services.audit import log_audit

router = APIRouter(prefix="/api/corrective-actions", tags=["corrective-actions"])


@router.get("", response_model=list[CorrectiveResponse])
async def list_actions(
    status: str | None = None,
    source: str | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    q = select(CorrectiveAction)
    if status:
        q = q.where(CorrectiveAction.status == status)
    if source:
        q = q.where(CorrectiveAction.source == source)
    return (await db.execute(q.order_by(CorrectiveAction.id.desc()))).scalars().all()


@router.post("", response_model=CorrectiveResponse, status_code=201)
async def create_action(
    body: CorrectiveCreate,
    current_user: User = Depends(require_role(["cpo", "security_officer"])),
    db: AsyncSession = Depends(get_db),
):
    ca = CorrectiveAction(**body.model_dump(), created_by=current_user.id)
    db.add(ca)
    await db.commit()
    await db.refresh(ca)
    return ca


@router.get("/{ca_id}", response_model=CorrectiveResponse)
async def get_action(ca_id: int, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    ca = (await db.execute(select(CorrectiveAction).where(CorrectiveAction.id == ca_id))).scalar_one_or_none()
    if not ca:
        raise HTTPException(404, "시정조치를 찾을 수 없습니다")
    return ca


@router.put("/{ca_id}", response_model=CorrectiveResponse)
async def update_action(
    ca_id: int,
    body: CorrectiveCreate,
    current_user: User = Depends(require_role(["cpo", "security_officer"])),
    db: AsyncSession = Depends(get_db),
):
    ca = (await db.execute(select(CorrectiveAction).where(CorrectiveAction.id == ca_id))).scalar_one_or_none()
    if not ca:
        raise HTTPException(404, "시정조치를 찾을 수 없습니다")
    if CorrectiveStatus(ca.status) not in (CorrectiveStatus.open, CorrectiveStatus.in_progress):
        raise HTTPException(400, f"현재 상태({ca.status})에서는 수정할 수 없습니다")
    for field, value in body.model_dump().items():
        setattr(ca, field, value)
    await db.commit()
    await db.refresh(ca)
    return ca


@router.post("/{ca_id}/complete")
async def complete_action(
    ca_id: int,
    body: CorrectiveComplete,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ca = (await db.execute(select(CorrectiveAction).where(CorrectiveAction.id == ca_id))).scalar_one_or_none()
    if not ca:
        raise HTTPException(404, "시정조치를 찾을 수 없습니다")
    if not body.result.strip():
        raise HTTPException(400, "조치 결과를 입력해주세요")
    ca.status = CorrectiveStatus.completed
    ca.result = body.result
    ca.evidence_id = body.evidence_id
    ca.completed_at = datetime.now(UTC)
    await db.commit()
    return {"message": "시정조치가 완료되었습니다"}


@router.post("/{ca_id}/verify")
async def verify_action(
    ca_id: int,
    body: CorrectiveVerify,
    current_user: User = Depends(require_role(["cpo", "security_officer"])),
    db: AsyncSession = Depends(get_db),
):
    ca = (await db.execute(select(CorrectiveAction).where(CorrectiveAction.id == ca_id))).scalar_one_or_none()
    if not ca:
        raise HTTPException(404, "시정조치를 찾을 수 없습니다")
    if CorrectiveStatus(ca.status) != CorrectiveStatus.completed:
        raise HTTPException(400, "조치가 완료된 후에만 검증할 수 있습니다")
    if ca.assigned_to == current_user.id and current_user.role != "cpo":
        raise HTTPException(400, "담당자는 직접 검증할 수 없습니다")

    ca.status = CorrectiveStatus.verified
    ca.verified_by = current_user.id
    ca.verified_at = datetime.now(UTC)
    ca.verification_note = body.verification_note

    audit_extra = {"self_verify": True} if ca.assigned_to == current_user.id else {}
    await log_audit(
        db, current_user.id, "UPDATE", "corrective_action", ca_id, new_values={"status": "verified", **audit_extra}
    )
    await db.commit()
    return {"message": "시정조치 검증이 완료되었습니다"}
