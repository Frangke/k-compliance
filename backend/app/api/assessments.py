"""Assessment CRUD (P1-2).

Round-aware grouping for ISMS-P snapshots + reports:
- audit_type: initial / surveillance / renewal
- scope_mode: all_items (auto-seed all 101) | subset (caller-picked sample)
- parent_assessment_id: links sub-round back to its initial/renewal

Existing snapshots without an assessment_id keep working; attaching to a
round is opt-in. A snapshot is only "in scope" for a round if its item
appears in the round's scope table.
"""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user, require_role
from app.models.assessment import (
    Assessment,
    AssessmentScopeItem,
    AssessmentStatus,
    AuditType,
    ScopeMode,
)
from app.models.compliance import ComplianceSnapshot
from app.models.isms import ISMSItem
from app.models.report import GeneratedReport
from app.models.user import User
from app.services.audit import log_audit

router = APIRouter(prefix="/api/assessments", tags=["assessments"])


class AssessmentCreate(BaseModel):
    code: str
    name: str
    framework: str = "kisa_isms_p_2023"
    audit_type: str = "initial"  # initial | surveillance | renewal
    scope_mode: str = "all_items"  # all_items | subset
    parent_assessment_id: int | None = None
    period_start: str
    period_end: str
    scope_note: str | None = None
    scope_item_codes: list[str] | None = None  # required when scope_mode=subset


class AssessmentUpdate(BaseModel):
    name: str | None = None
    period_start: str | None = None
    period_end: str | None = None
    scope_note: str | None = None


class AssessmentTransition(BaseModel):
    status: str


class ScopeItemsUpdate(BaseModel):
    add_item_codes: list[str] | None = None
    remove_item_codes: list[str] | None = None


async def _count_progress(db: AsyncSession, assessment_id: int) -> dict:
    """Total scope items + how many already have a snapshot in this round."""
    scope_n = (
        await db.execute(
            select(func.count())
            .select_from(AssessmentScopeItem)
            .where(AssessmentScopeItem.assessment_id == assessment_id)
        )
    ).scalar() or 0
    # distinct items that have at least one snapshot for this assessment
    done_n = (
        await db.execute(
            select(func.count(func.distinct(ComplianceSnapshot.item_id))).where(
                ComplianceSnapshot.assessment_id == assessment_id
            )
        )
    ).scalar() or 0
    return {"scope_total": scope_n, "assessed_count": done_n}


def _dict(a: Assessment, *, snapshot_count: int = 0, report_count: int = 0, progress: dict | None = None) -> dict:
    return {
        "id": a.id,
        "code": a.code,
        "name": a.name,
        "framework": a.framework,
        "audit_type": a.audit_type.value if hasattr(a.audit_type, "value") else a.audit_type,
        "scope_mode": a.scope_mode.value if hasattr(a.scope_mode, "value") else a.scope_mode,
        "parent_assessment_id": a.parent_assessment_id,
        "period_start": a.period_start.isoformat(),
        "period_end": a.period_end.isoformat(),
        "scope_note": a.scope_note,
        "status": a.status.value if hasattr(a.status, "value") else a.status,
        "created_by": a.created_by,
        "created_at": a.created_at.isoformat() if a.created_at else None,
        "closed_at": a.closed_at.isoformat() if a.closed_at else None,
        "snapshot_count": snapshot_count,
        "report_count": report_count,
        "scope_total": (progress or {}).get("scope_total", 0),
        "assessed_count": (progress or {}).get("assessed_count", 0),
    }


@router.get("")
async def list_assessments(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    rows = (await db.execute(select(Assessment).order_by(desc(Assessment.created_at)))).scalars().all()
    out = []
    for a in rows:
        snap_n = (
            await db.execute(
                select(func.count()).select_from(ComplianceSnapshot).where(ComplianceSnapshot.assessment_id == a.id)
            )
        ).scalar() or 0
        rpt_n = (
            await db.execute(
                select(func.count()).select_from(GeneratedReport).where(GeneratedReport.assessment_id == a.id)
            )
        ).scalar() or 0
        progress = await _count_progress(db, a.id)
        out.append(_dict(a, snapshot_count=snap_n, report_count=rpt_n, progress=progress))
    return out


@router.get("/{assessment_id}")
async def get_assessment(
    assessment_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    a = (await db.execute(select(Assessment).where(Assessment.id == assessment_id))).scalar_one_or_none()
    if not a:
        raise HTTPException(status_code=404, detail="평가 세션을 찾을 수 없습니다")
    snap_n = (
        await db.execute(
            select(func.count()).select_from(ComplianceSnapshot).where(ComplianceSnapshot.assessment_id == a.id)
        )
    ).scalar() or 0
    rpt_n = (
        await db.execute(select(func.count()).select_from(GeneratedReport).where(GeneratedReport.assessment_id == a.id))
    ).scalar() or 0
    progress = await _count_progress(db, a.id)
    return _dict(a, snapshot_count=snap_n, report_count=rpt_n, progress=progress)


@router.get("/{assessment_id}/scope")
async def list_scope_items(
    assessment_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List items in this assessment's scope, with per-item completion flag."""
    a = (await db.execute(select(Assessment).where(Assessment.id == assessment_id))).scalar_one_or_none()
    if not a:
        raise HTTPException(status_code=404, detail="평가 세션을 찾을 수 없습니다")

    rows = (
        await db.execute(
            select(ISMSItem, AssessmentScopeItem.is_sample)
            .join(AssessmentScopeItem, AssessmentScopeItem.item_id == ISMSItem.id)
            .where(AssessmentScopeItem.assessment_id == assessment_id)
            .order_by(ISMSItem.code)
        )
    ).all()

    # Which items already have a snapshot for this round?
    assessed_item_ids = {
        r
        for (r,) in (
            await db.execute(
                select(ComplianceSnapshot.item_id).distinct().where(ComplianceSnapshot.assessment_id == assessment_id)
            )
        ).all()
    }

    return [
        {
            "item_id": item.id,
            "code": item.code,
            "name": item.name,
            "is_sample": is_sample,
            "assessed": item.id in assessed_item_ids,
        }
        for item, is_sample in rows
    ]


async def _seed_scope(
    db: AsyncSession, assessment_id: int, scope_mode: ScopeMode, item_codes: list[str] | None
) -> None:
    """Populate assessment_scope_items for a newly created assessment."""
    if scope_mode == ScopeMode.all_items:
        items = (await db.execute(select(ISMSItem.id))).scalars().all()
        for item_id in items:
            db.add(AssessmentScopeItem(assessment_id=assessment_id, item_id=item_id, is_sample=False))
    else:  # subset
        if not item_codes:
            raise HTTPException(status_code=400, detail="샘플 항목 코드 목록이 필요합니다")
        resolved = (await db.execute(select(ISMSItem.id, ISMSItem.code).where(ISMSItem.code.in_(item_codes)))).all()
        known = {code for _, code in resolved}
        missing = [c for c in item_codes if c not in known]
        if missing:
            raise HTTPException(status_code=400, detail=f"존재하지 않는 항목 코드: {', '.join(missing)}")
        for item_id, _ in resolved:
            db.add(AssessmentScopeItem(assessment_id=assessment_id, item_id=item_id, is_sample=True))


@router.post("", status_code=201)
async def create_assessment(
    body: AssessmentCreate,
    request: Request,
    current_user: User = Depends(require_role(["cpo", "security_officer"])),
    db: AsyncSession = Depends(get_db),
):
    from datetime import date as _date

    try:
        ps = _date.fromisoformat(body.period_start)
        pe = _date.fromisoformat(body.period_end)
    except ValueError:
        raise HTTPException(status_code=400, detail="날짜 형식이 올바르지 않습니다 (YYYY-MM-DD)")
    if ps > pe:
        raise HTTPException(status_code=400, detail="시작일이 종료일보다 늦을 수 없습니다")

    try:
        audit_type = AuditType(body.audit_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"알 수 없는 심사 유형: {body.audit_type}")
    try:
        scope_mode = ScopeMode(body.scope_mode)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"알 수 없는 범위 모드: {body.scope_mode}")

    # Surveillance/renewal should point at an initial or renewal ancestor.
    # Initial shouldn't have a parent. Validate the FK target exists.
    if body.parent_assessment_id is not None:
        parent = (
            await db.execute(select(Assessment).where(Assessment.id == body.parent_assessment_id))
        ).scalar_one_or_none()
        if not parent:
            raise HTTPException(status_code=400, detail="상위 평가 세션을 찾을 수 없습니다")
        if audit_type == AuditType.initial:
            raise HTTPException(status_code=400, detail="최초 심사는 상위 심사를 가질 수 없습니다")
    elif audit_type in (AuditType.surveillance, AuditType.renewal):
        # Not fatal — first surveillance/renewal sometimes pre-dates this app
        # being used for the initial round. Warn via audit_log but allow.
        pass

    existing = (await db.execute(select(Assessment).where(Assessment.code == body.code))).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail=f"이미 존재하는 평가 코드입니다: {body.code}")

    a = Assessment(
        code=body.code,
        name=body.name,
        framework=body.framework,
        audit_type=audit_type,
        scope_mode=scope_mode,
        parent_assessment_id=body.parent_assessment_id,
        period_start=ps,
        period_end=pe,
        scope_note=body.scope_note,
        status=AssessmentStatus.draft,
        created_by=current_user.id,
    )
    db.add(a)
    await db.flush()

    await _seed_scope(db, a.id, scope_mode, body.scope_item_codes)
    await db.flush()

    scope_n = (
        await db.execute(
            select(func.count()).select_from(AssessmentScopeItem).where(AssessmentScopeItem.assessment_id == a.id)
        )
    ).scalar() or 0

    await log_audit(
        db,
        current_user.id,
        "create",
        "assessment",
        a.id,
        new_values={
            "code": a.code,
            "name": a.name,
            "audit_type": audit_type.value,
            "scope_mode": scope_mode.value,
            "scope_total": scope_n,
            "parent_assessment_id": body.parent_assessment_id,
            "period": f"{ps}~{pe}",
        },
        request=request,
    )
    await db.commit()
    await db.refresh(a)
    progress = await _count_progress(db, a.id)
    return _dict(a, snapshot_count=0, report_count=0, progress=progress)


@router.put("/{assessment_id}")
async def update_assessment(
    assessment_id: int,
    body: AssessmentUpdate,
    request: Request,
    current_user: User = Depends(require_role(["cpo", "security_officer"])),
    db: AsyncSession = Depends(get_db),
):
    a = (await db.execute(select(Assessment).where(Assessment.id == assessment_id))).scalar_one_or_none()
    if not a:
        raise HTTPException(status_code=404, detail="평가 세션을 찾을 수 없습니다")
    if a.status == AssessmentStatus.closed:
        raise HTTPException(status_code=400, detail="종료된 평가는 수정할 수 없습니다")

    from datetime import date as _date

    old = {
        "name": a.name,
        "period_start": str(a.period_start),
        "period_end": str(a.period_end),
        "scope_note": a.scope_note,
    }
    if body.name is not None:
        a.name = body.name
    if body.period_start is not None:
        a.period_start = _date.fromisoformat(body.period_start)
    if body.period_end is not None:
        a.period_end = _date.fromisoformat(body.period_end)
    if a.period_start > a.period_end:
        raise HTTPException(status_code=400, detail="시작일이 종료일보다 늦을 수 없습니다")
    if body.scope_note is not None:
        a.scope_note = body.scope_note

    await log_audit(
        db,
        current_user.id,
        "update",
        "assessment",
        a.id,
        old_values=old,
        new_values={
            "name": a.name,
            "period_start": str(a.period_start),
            "period_end": str(a.period_end),
            "scope_note": a.scope_note,
        },
        request=request,
    )
    await db.commit()
    await db.refresh(a)
    progress = await _count_progress(db, a.id)
    return _dict(a, progress=progress)


@router.post("/{assessment_id}/scope")
async def update_scope(
    assessment_id: int,
    body: ScopeItemsUpdate,
    request: Request,
    current_user: User = Depends(require_role(["cpo", "security_officer"])),
    db: AsyncSession = Depends(get_db),
):
    """Add or remove items from an existing assessment's scope.

    Intended for surveillance rounds that grow or shrink after kickoff, and
    to let auditors graft an extra item into an initial round without
    cloning. Closed rounds are read-only.
    """
    a = (await db.execute(select(Assessment).where(Assessment.id == assessment_id))).scalar_one_or_none()
    if not a:
        raise HTTPException(status_code=404, detail="평가 세션을 찾을 수 없습니다")
    if a.status == AssessmentStatus.closed:
        raise HTTPException(status_code=400, detail="종료된 평가의 범위는 수정할 수 없습니다")

    added: list[str] = []
    removed: list[str] = []

    if body.add_item_codes:
        rows = (
            await db.execute(select(ISMSItem.id, ISMSItem.code).where(ISMSItem.code.in_(body.add_item_codes)))
        ).all()
        known = {code: iid for iid, code in rows}
        missing = [c for c in body.add_item_codes if c not in known]
        if missing:
            raise HTTPException(status_code=400, detail=f"존재하지 않는 항목 코드: {', '.join(missing)}")
        existing = {
            iid
            for (iid,) in (
                await db.execute(
                    select(AssessmentScopeItem.item_id).where(
                        AssessmentScopeItem.assessment_id == a.id, AssessmentScopeItem.item_id.in_(known.values())
                    )
                )
            ).all()
        }
        for code, iid in known.items():
            if iid not in existing:
                # Manually added after kickoff — mark as sample so the
                # surveillance-style filtering still picks them up correctly.
                db.add(
                    AssessmentScopeItem(
                        assessment_id=a.id,
                        item_id=iid,
                        is_sample=(a.scope_mode == ScopeMode.subset),
                    )
                )
                added.append(code)

    if body.remove_item_codes:
        rows = (
            await db.execute(select(ISMSItem.id, ISMSItem.code).where(ISMSItem.code.in_(body.remove_item_codes)))
        ).all()
        ids_to_remove = [iid for iid, _ in rows]
        removed_rows = (
            await db.execute(
                select(AssessmentScopeItem, ISMSItem.code)
                .join(ISMSItem, ISMSItem.id == AssessmentScopeItem.item_id)
                .where(AssessmentScopeItem.assessment_id == a.id, AssessmentScopeItem.item_id.in_(ids_to_remove))
            )
        ).all()
        for scope_row, code in removed_rows:
            await db.delete(scope_row)
            removed.append(code)

    await log_audit(
        db,
        current_user.id,
        "update",
        "assessment_scope",
        a.id,
        new_values={"added": added, "removed": removed},
        request=request,
    )
    await db.commit()

    progress = await _count_progress(db, a.id)
    return {
        "added": added,
        "removed": removed,
        "scope_total": progress["scope_total"],
        "assessed_count": progress["assessed_count"],
    }


@router.post("/{assessment_id}/transition")
async def transition_assessment(
    assessment_id: int,
    body: AssessmentTransition,
    request: Request,
    current_user: User = Depends(require_role(["cpo", "security_officer"])),
    db: AsyncSession = Depends(get_db),
):
    a = (await db.execute(select(Assessment).where(Assessment.id == assessment_id))).scalar_one_or_none()
    if not a:
        raise HTTPException(status_code=404, detail="평가 세션을 찾을 수 없습니다")

    allowed = {
        AssessmentStatus.draft: {AssessmentStatus.active},
        AssessmentStatus.active: {AssessmentStatus.closed},
        AssessmentStatus.closed: set(),
    }
    try:
        target = AssessmentStatus(body.status)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"알 수 없는 상태: {body.status}")
    if target not in allowed[a.status]:
        raise HTTPException(
            status_code=400,
            detail=f"{a.status.value} → {target.value} 전이는 허용되지 않습니다",
        )

    old_status = a.status
    a.status = target
    if target == AssessmentStatus.closed:
        a.closed_at = datetime.now(UTC)

    action = "submit" if target == AssessmentStatus.active else "complete"
    await log_audit(
        db,
        current_user.id,
        action,
        "assessment",
        a.id,
        old_values={"status": old_status.value},
        new_values={"status": target.value},
        request=request,
    )
    await db.commit()
    await db.refresh(a)
    progress = await _count_progress(db, a.id)
    return _dict(a, progress=progress)


@router.delete("/{assessment_id}")
async def delete_assessment(
    assessment_id: int,
    request: Request,
    current_user: User = Depends(require_role(["cpo"])),
    db: AsyncSession = Depends(get_db),
):
    a = (await db.execute(select(Assessment).where(Assessment.id == assessment_id))).scalar_one_or_none()
    if not a:
        raise HTTPException(status_code=404, detail="평가 세션을 찾을 수 없습니다")
    if a.status != AssessmentStatus.draft:
        raise HTTPException(status_code=400, detail="활성화되었거나 종료된 평가는 삭제할 수 없습니다 (종료만 가능)")

    await log_audit(
        db,
        current_user.id,
        "delete",
        "assessment",
        a.id,
        old_values={"code": a.code, "name": a.name, "status": a.status.value},
        request=request,
    )
    await db.delete(a)
    await db.commit()
    return {"message": "평가 세션이 삭제되었습니다"}
