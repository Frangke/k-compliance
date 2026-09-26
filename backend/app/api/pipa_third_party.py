from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user, require_role
from app.models.pipa import ThirdPartyProcessor
from app.models.user import User
from app.schemas.pipa import ThirdPartyCreate, ThirdPartyResponse
from app.services.audit import log_audit

router = APIRouter(prefix="/api/pipa/third-party", tags=["pipa-third-party"])


@router.get("", response_model=list[ThirdPartyResponse])
async def list_processors(
    is_active: bool | None = None, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    q = select(ThirdPartyProcessor)
    if is_active is not None:
        q = q.where(ThirdPartyProcessor.is_active == is_active)
    return (await db.execute(q.order_by(ThirdPartyProcessor.id.desc()))).scalars().all()


@router.post("", response_model=ThirdPartyResponse, status_code=201)
async def create_processor(
    body: ThirdPartyCreate,
    request: Request,
    current_user: User = Depends(require_role(["cpo", "security_officer"])),
    db: AsyncSession = Depends(get_db),
):
    if body.contract_start > body.contract_end:
        raise HTTPException(400, "계약 시작일이 종료일보다 늦을 수 없습니다")
    if body.is_sub_delegated and not body.parent_processor_id:
        raise HTTPException(400, "재위탁 시 원 위탁업체를 지정해주세요")
    proc = ThirdPartyProcessor(**body.model_dump(), created_by=current_user.id)
    db.add(proc)
    await db.flush()
    await log_audit(
        db,
        current_user.id,
        "create",
        "third_party_processor",
        proc.id,
        new_values={
            "company_name": proc.company_name,
            "contract_start": str(proc.contract_start),
            "contract_end": str(proc.contract_end),
            "is_sub_delegated": proc.is_sub_delegated,
            "parent_processor_id": proc.parent_processor_id,
        },
        request=request,
    )
    await db.commit()
    await db.refresh(proc)
    return proc


@router.put("/{proc_id}", response_model=ThirdPartyResponse)
async def update_processor(
    proc_id: int,
    body: ThirdPartyCreate,
    request: Request,
    current_user: User = Depends(require_role(["cpo", "security_officer"])),
    db: AsyncSession = Depends(get_db),
):
    proc = (await db.execute(select(ThirdPartyProcessor).where(ThirdPartyProcessor.id == proc_id))).scalar_one_or_none()
    if not proc:
        raise HTTPException(404, "위탁업체를 찾을 수 없습니다")
    if body.contract_start > body.contract_end:
        raise HTTPException(400, "계약 시작일이 종료일보다 늦을 수 없습니다")
    changes = body.model_dump()
    for field, value in changes.items():
        setattr(proc, field, value)
    await log_audit(
        db, current_user.id, "update", "third_party_processor", proc.id, new_values=changes, request=request
    )
    await db.commit()
    await db.refresh(proc)
    return proc


@router.post("/{proc_id}/audit")
async def record_audit(
    proc_id: int,
    request: Request,
    audit_result: str = Query(...),
    current_user: User = Depends(require_role(["cpo", "security_officer"])),
    db: AsyncSession = Depends(get_db),
):
    proc = (await db.execute(select(ThirdPartyProcessor).where(ThirdPartyProcessor.id == proc_id))).scalar_one_or_none()
    if not proc:
        raise HTTPException(404, "위탁업체를 찾을 수 없습니다")

    # Separation of duties (hard): the person who registered the contract
    # cannot also sign off on its security audit — objectivity is the whole
    # point of the audit. CPO is exempt but the bypass is tagged.
    audit_extra: dict = {}
    if proc.created_by and proc.created_by == current_user.id:
        if current_user.role != "cpo":
            raise HTTPException(400, "계약 등록자는 점검 결과를 직접 기록할 수 없습니다 (직무분리)")
        audit_extra["self_audit"] = True

    proc.security_audit_done = True
    proc.audit_date = date.today()
    proc.audit_result = audit_result
    await log_audit(
        db,
        current_user.id,
        "audit.record",
        "third_party_processor",
        proc_id,
        new_values={"audit_date": str(proc.audit_date), "audit_result": audit_result[:500], **audit_extra},
        request=request,
    )
    await db.commit()
    return {"message": "점검 기록이 추가되었습니다"}
