from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user, require_role
from app.models.pipa import ConsentTemplate, ConsentVersion
from app.models.user import User
from app.schemas.pipa import (
    ConsentTemplateCreate,
    ConsentTemplateResponse,
    ConsentVersionCreate,
    ConsentVersionResponse,
)
from app.services.audit import log_audit

router = APIRouter(prefix="/api/pipa/consent", tags=["pipa-consent"])


@router.get("", response_model=list[ConsentTemplateResponse])
async def list_templates(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ConsentTemplate).order_by(ConsentTemplate.id.desc()))
    return result.scalars().all()


@router.post("", response_model=ConsentTemplateResponse, status_code=201)
async def create_template(
    body: ConsentTemplateCreate,
    request: Request,
    current_user: User = Depends(require_role(["cpo", "security_officer"])),
    db: AsyncSession = Depends(get_db),
):
    t = ConsentTemplate(**body.model_dump(), created_by=current_user.id)
    db.add(t)
    await db.flush()
    await log_audit(
        db, current_user.id, "create", "consent_template", t.id, new_values={"name": t.name}, request=request
    )
    await db.commit()
    await db.refresh(t)
    return t


@router.post("/{template_id}/versions", response_model=ConsentVersionResponse, status_code=201)
async def create_version(
    template_id: int,
    body: ConsentVersionCreate,
    request: Request,
    current_user: User = Depends(require_role(["cpo", "security_officer"])),
    db: AsyncSession = Depends(get_db),
):
    t = (await db.execute(select(ConsentTemplate).where(ConsentTemplate.id == template_id))).scalar_one_or_none()
    if not t:
        raise HTTPException(404, "템플릿을 찾을 수 없습니다")
    max_ver = (
        await db.execute(
            select(func.max(ConsentVersion.version_number)).where(ConsentVersion.template_id == template_id)
        )
    ).scalar() or 0
    v = ConsentVersion(
        template_id=template_id, version_number=max_ver + 1, content=body.content, effective_date=body.effective_date
    )
    db.add(v)
    await db.flush()
    await log_audit(
        db,
        current_user.id,
        "create",
        "consent_version",
        v.id,
        new_values={"template_id": template_id, "version_number": v.version_number},
        request=request,
    )
    await db.commit()
    await db.refresh(v)
    return v


@router.post("/{template_id}/versions/{ver}/publish")
async def publish_version(
    template_id: int,
    ver: int,
    request: Request,
    current_user: User = Depends(require_role(["cpo", "security_officer"])),
    db: AsyncSession = Depends(get_db),
):
    v = (
        await db.execute(
            select(ConsentVersion).where(
                ConsentVersion.template_id == template_id, ConsentVersion.version_number == ver
            )
        )
    ).scalar_one_or_none()
    if not v:
        raise HTTPException(404, "버전을 찾을 수 없습니다")
    if v.is_published:
        raise HTTPException(400, "이미 발행된 버전입니다")
    v.is_published = True
    await log_audit(
        db,
        current_user.id,
        "publish",
        "consent_version",
        v.id,
        new_values={"template_id": template_id, "version_number": ver},
        request=request,
    )
    await db.commit()
    return {"message": f"버전 {ver}이 발행되었습니다"}
