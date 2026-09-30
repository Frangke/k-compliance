from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user, require_role
from app.models.compliance import ChecklistResponse as ChecklistResponseModel
from app.models.compliance import ComplianceLevel, ComplianceSnapshot
from app.models.evidence import Evidence, EvidenceItemLink, EvidenceStatus
from app.models.isms import ISMSChecklist, ISMSDomain, ISMSItem, ISMSItemAssignment, ISMSSubdomain
from app.models.user import User
from app.schemas.isms import (
    AssignmentCreate,
    AssignmentResponse,
    ComplianceSummary,
    DomainResponse,
    ItemListResponse,
    ItemResponse,
    SubdomainResponse,
)
from app.services.audit import log_audit

router = APIRouter(prefix="/api/isms", tags=["isms"])


# --- Helper: latest snapshot per item ---
def _latest_snapshot_ids():
    """Subquery returning the latest ComplianceSnapshot.id per item_id."""
    return select(func.max(ComplianceSnapshot.id)).group_by(ComplianceSnapshot.item_id)


# --- Domains tree ---
@router.get("/domains", response_model=list[DomainResponse])
async def list_domains(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(ISMSDomain).order_by(ISMSDomain.sort_order))
    domains = result.scalars().all()

    response = []
    for domain in domains:
        subs_result = await db.execute(
            select(ISMSSubdomain).where(ISMSSubdomain.domain_id == domain.id).order_by(ISMSSubdomain.sort_order)
        )
        subs = []
        for sub in subs_result.scalars():
            items_result = await db.execute(
                select(ISMSItem).where(ISMSItem.subdomain_id == sub.id).order_by(ISMSItem.sort_order)
            )
            subs.append(
                SubdomainResponse(
                    id=sub.id,
                    code=sub.code,
                    name=sub.name,
                    description=sub.description,
                    items=[ItemResponse.model_validate(i) for i in items_result.scalars()],
                )
            )
        response.append(
            DomainResponse(
                id=domain.id,
                code=domain.code,
                name=domain.name,
                description=domain.description,
                subdomains=subs,
            )
        )
    return response


# --- Items list ---
@router.get("/items", response_model=ItemListResponse)
async def list_items(
    domain: str | None = None,
    search: str | None = None,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    q = select(ISMSItem).join(ISMSSubdomain).join(ISMSDomain)
    count_q = select(func.count()).select_from(ISMSItem).join(ISMSSubdomain).join(ISMSDomain)

    if domain:
        q = q.where(ISMSDomain.code == domain)
        count_q = count_q.where(ISMSDomain.code == domain)
    if search:
        like = f"%{search}%"
        q = q.where(or_(ISMSItem.name.ilike(like), ISMSItem.code.ilike(like), ISMSItem.description.ilike(like)))
        count_q = count_q.where(
            or_(ISMSItem.name.ilike(like), ISMSItem.code.ilike(like), ISMSItem.description.ilike(like))
        )

    total = (await db.execute(count_q)).scalar()
    result = await db.execute(q.order_by(ISMSItem.code).offset((page - 1) * size).limit(size))
    items = []
    for item in result.scalars():
        ev_count = (
            await db.execute(
                select(func.count()).select_from(EvidenceItemLink).where(EvidenceItemLink.item_id == item.id)
            )
        ).scalar()
        cl_count = (
            await db.execute(select(func.count()).select_from(ISMSChecklist).where(ISMSChecklist.item_id == item.id))
        ).scalar()

        ir = ItemResponse.model_validate(item)
        ir.evidence_count = ev_count
        ir.checklist_total = cl_count
        items.append(ir)

    return ItemListResponse(items=items, total=total)


# --- Item detail ---
@router.get("/items/{code}", response_model=ItemResponse)
async def get_item(
    code: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(ISMSItem).where(ISMSItem.code == code))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="항목을 찾을 수 없습니다")

    ev_count = (
        await db.execute(select(func.count()).select_from(EvidenceItemLink).where(EvidenceItemLink.item_id == item.id))
    ).scalar()
    cl_count = (
        await db.execute(select(func.count()).select_from(ISMSChecklist).where(ISMSChecklist.item_id == item.id))
    ).scalar()

    ir = ItemResponse.model_validate(item)
    ir.evidence_count = ev_count
    ir.checklist_total = cl_count
    return ir


# --- Compliance status by item (latest snapshot per item) ---
@router.get("/compliance-detail")
async def compliance_detail(
    status_filter: str | None = Query(None, description="compliant/partial/non_compliant/not_applicable/not_assessed"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Returns per-item compliance status (latest snapshot per item)."""
    items_result = await db.execute(
        select(ISMSItem, ISMSDomain.code.label("domain_code"), ISMSDomain.name.label("domain_name"))
        .select_from(ISMSItem)
        .join(ISMSSubdomain, ISMSItem.subdomain_id == ISMSSubdomain.id)
        .join(ISMSDomain, ISMSSubdomain.domain_id == ISMSDomain.id)
        .order_by(ISMSItem.code)
    )

    latest_snaps = await db.execute(select(ComplianceSnapshot).where(ComplianceSnapshot.id.in_(_latest_snapshot_ids())))
    snap_map = {s.item_id: s for s in latest_snaps.scalars()}

    rows = []
    for row in items_result:
        item = row[0]
        snap = snap_map.get(item.id)
        item_status = snap.status.value if snap else "not_assessed"

        if status_filter and item_status != status_filter:
            continue

        rows.append(
            {
                "code": item.code,
                "name": item.name,
                "domain_code": row.domain_code,
                "domain_name": row.domain_name,
                "status": item_status,
                "checklist_checked": snap.checklist_checked if snap else 0,
                "checklist_total": snap.checklist_total if snap else 0,
                "evidence_approved": snap.evidence_approved if snap else 0,
                "evidence_count": snap.evidence_count if snap else 0,
                "assessed_at": snap.assessed_at.isoformat() if snap and snap.assessed_at else None,
                "notes": snap.notes if snap else None,
            }
        )

    return rows


@router.get("/compliance-detail/csv")
async def compliance_detail_csv(
    status_filter: str | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """CSV export of compliance detail."""
    import csv
    import io

    from fastapi.responses import StreamingResponse

    data = await compliance_detail(status_filter=status_filter, current_user=current_user, db=db)

    output = io.StringIO()
    output.write("\ufeff")
    writer = csv.writer(output)
    writer.writerow(["항목코드", "항목명", "도메인", "준수상태", "체크리스트", "증적(승인/전체)", "평가일시", "메모"])

    status_kr = {
        "compliant": "준수",
        "partial": "부분준수",
        "non_compliant": "미준수",
        "not_applicable": "해당없음",
        "not_assessed": "미평가",
    }
    for r in data:
        writer.writerow(
            [
                r["code"],
                r["name"],
                f"{r['domain_code']}. {r['domain_name']}",
                status_kr.get(r["status"], r["status"]),
                f"{r['checklist_checked']}/{r['checklist_total']}",
                f"{r['evidence_approved']}/{r['evidence_count']}",
                r["assessed_at"][:16].replace("T", " ") if r["assessed_at"] else "",
                r["notes"] or "",
            ]
        )

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=compliance_detail.csv"},
    )


# --- Compliance summary ---
@router.get("/compliance-summary", response_model=list[ComplianceSummary])
async def compliance_summary(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    domains_result = await db.execute(select(ISMSDomain).order_by(ISMSDomain.sort_order))
    summaries = []
    for domain in domains_result.scalars():
        item_count = (
            await db.execute(
                select(func.count())
                .select_from(ISMSItem)
                .join(ISMSSubdomain)
                .where(ISMSSubdomain.domain_id == domain.id)
            )
        ).scalar()

        item_ids_in_domain = select(ISMSItem.id).join(ISMSSubdomain).where(ISMSSubdomain.domain_id == domain.id)
        latest_ids = (
            select(func.max(ComplianceSnapshot.id))
            .where(ComplianceSnapshot.item_id.in_(item_ids_in_domain))
            .group_by(ComplianceSnapshot.item_id)
        )
        snap_q = (
            select(ComplianceSnapshot.status, func.count())
            .where(ComplianceSnapshot.id.in_(latest_ids))
            .group_by(ComplianceSnapshot.status)
        )
        snap_result = await db.execute(snap_q)
        counts = dict(snap_result.all())

        compliant = counts.get("compliant", 0)
        partial = counts.get("partial", 0)
        non_compliant = counts.get("non_compliant", 0)
        assessed = compliant + partial + non_compliant + counts.get("not_applicable", 0)
        not_assessed = item_count - assessed
        rate = (compliant / item_count * 100) if item_count > 0 else 0

        summaries.append(
            ComplianceSummary(
                domain_code=domain.code,
                domain_name=domain.name,
                total=item_count,
                compliant=compliant,
                partial=partial,
                non_compliant=non_compliant,
                not_assessed=not_assessed,
                rate=round(rate, 1),
            )
        )
    return summaries


# --- Per-item compliance status map (for item list tree view) ---
@router.get("/compliance-status-map")
async def compliance_status_map(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Returns {item_code: status} map for all items (latest snapshot per item)."""
    result = await db.execute(
        select(ISMSItem.code, ComplianceSnapshot.status)
        .join(ISMSItem, ComplianceSnapshot.item_id == ISMSItem.id)
        .where(ComplianceSnapshot.id.in_(_latest_snapshot_ids()))
    )
    return {code: status for code, status in result.all()}


# --- Item assignments ---
@router.get("/items/{code}/assignments", response_model=list[AssignmentResponse])
async def list_assignments(
    code: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    item = (await db.execute(select(ISMSItem).where(ISMSItem.code == code))).scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="항목을 찾을 수 없습니다")

    result = await db.execute(
        select(ISMSItemAssignment, User.username, User.name)
        .join(User, ISMSItemAssignment.user_id == User.id)
        .where(ISMSItemAssignment.item_id == item.id)
    )
    return [
        AssignmentResponse(
            id=a.id,
            user_id=a.user_id,
            username=username,
            name=name,
            role_in_item=a.role_in_item,
            assigned_at=a.assigned_at,
        )
        for a, username, name in result.all()
    ]


@router.post("/items/{code}/assignments", status_code=201)
async def create_assignment(
    code: str,
    body: AssignmentCreate,
    request: Request,
    current_user: User = Depends(require_role(["cpo", "security_officer"])),
    db: AsyncSession = Depends(get_db),
):
    item = (await db.execute(select(ISMSItem).where(ISMSItem.code == code))).scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="항목을 찾을 수 없습니다")

    assignment = ISMSItemAssignment(
        item_id=item.id,
        user_id=body.user_id,
        role_in_item=body.role_in_item,
        assigned_by=current_user.id,
    )
    db.add(assignment)
    await db.flush()
    await log_audit(
        db,
        current_user.id,
        "assign",
        "isms_item_assignment",
        assignment.id,
        new_values={"item_code": code, "user_id": body.user_id, "role_in_item": body.role_in_item},
        request=request,
    )
    await db.commit()
    return {"message": "담당자가 배정되었습니다"}


@router.delete("/items/{code}/assignments/{user_id}")
async def delete_assignment(
    code: str,
    user_id: int,
    request: Request,
    current_user: User = Depends(require_role(["cpo", "security_officer"])),
    db: AsyncSession = Depends(get_db),
):
    item = (await db.execute(select(ISMSItem).where(ISMSItem.code == code))).scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="항목을 찾을 수 없습니다")

    result = await db.execute(
        select(ISMSItemAssignment).where(ISMSItemAssignment.item_id == item.id, ISMSItemAssignment.user_id == user_id)
    )
    assignment = result.scalar_one_or_none()
    if not assignment:
        raise HTTPException(status_code=404, detail="배정 정보를 찾을 수 없습니다")

    assignment_id = assignment.id
    await db.delete(assignment)
    await log_audit(
        db,
        current_user.id,
        "revoke",
        "isms_item_assignment",
        assignment_id,
        old_values={"item_code": code, "user_id": user_id},
        request=request,
    )
    await db.commit()
    return {"message": "담당자 배정이 해제되었습니다"}


# --- My items ---
@router.get("/my-items", response_model=ItemListResponse)
async def my_items(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ISMSItem)
        .join(ISMSItemAssignment, ISMSItemAssignment.item_id == ISMSItem.id)
        .where(ISMSItemAssignment.user_id == current_user.id)
        .order_by(ISMSItem.code)
    )
    items = [ItemResponse.model_validate(i) for i in result.scalars()]
    return ItemListResponse(items=items, total=len(items))


# ============================================================
# T2.2 — Checklists (no period — current state only)
# ============================================================


class ChecklistItemOut(BaseModel):
    id: int
    question: str
    sort_order: int
    is_checked: bool = False
    evidence_id: int | None = None
    evidence_warning: str | None = None
    notes: str | None = None
    checked_by: int | None = None
    checked_at: datetime | None = None


class ChecklistRespondIn(BaseModel):
    is_checked: bool = False
    evidence_id: int | None = None
    notes: str | None = None


@router.get("/items/{code}/checklists")
async def get_checklists(
    code: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    item = (await db.execute(select(ISMSItem).where(ISMSItem.code == code))).scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="항목을 찾을 수 없습니다")

    checklists = (
        (
            await db.execute(
                select(ISMSChecklist).where(ISMSChecklist.item_id == item.id).order_by(ISMSChecklist.sort_order)
            )
        )
        .scalars()
        .all()
    )

    result = []
    for cl in checklists:
        resp = (
            await db.execute(
                select(ChecklistResponseModel).where(
                    ChecklistResponseModel.checklist_id == cl.id,
                )
            )
        ).scalar_one_or_none()

        out = ChecklistItemOut(id=cl.id, question=cl.question, sort_order=cl.sort_order)
        if resp:
            out.is_checked = resp.is_checked
            out.evidence_id = resp.evidence_id
            out.notes = resp.notes
            out.checked_by = resp.checked_by
            out.checked_at = resp.checked_at
            if resp.evidence_id:
                ev = (
                    await db.execute(select(Evidence.status).where(Evidence.id == resp.evidence_id))
                ).scalar_one_or_none()
                if ev and ev in (EvidenceStatus.expired, EvidenceStatus.replaced):
                    out.evidence_warning = "연결된 증적이 만료/대체되었습니다"
        result.append(out)

    return {"item_code": code, "checklists": result}


@router.post("/items/{code}/checklists/{checklist_id}/respond")
async def respond_checklist(
    code: str,
    checklist_id: int,
    body: ChecklistRespondIn,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    item = (await db.execute(select(ISMSItem).where(ISMSItem.code == code))).scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="항목을 찾을 수 없습니다")

    cl = (
        await db.execute(
            select(ISMSChecklist).where(ISMSChecklist.id == checklist_id, ISMSChecklist.item_id == item.id)
        )
    ).scalar_one_or_none()
    if not cl:
        raise HTTPException(status_code=404, detail="체크리스트를 찾을 수 없습니다")

    # Upsert response (one per checklist)
    existing = (
        await db.execute(
            select(ChecklistResponseModel).where(
                ChecklistResponseModel.checklist_id == checklist_id,
            )
        )
    ).scalar_one_or_none()

    if existing:
        existing.is_checked = body.is_checked
        existing.evidence_id = body.evidence_id
        existing.notes = body.notes
        existing.checked_by = current_user.id
        existing.checked_at = datetime.now(UTC)
    else:
        db.add(
            ChecklistResponseModel(
                checklist_id=checklist_id,
                is_checked=body.is_checked,
                evidence_id=body.evidence_id,
                notes=body.notes,
                checked_by=current_user.id,
                checked_at=datetime.now(UTC),
            )
        )

    await log_audit(
        db,
        current_user.id,
        "update",
        "checklist_response",
        checklist_id,
        new_values={"item_code": code, "is_checked": body.is_checked, "evidence_id": body.evidence_id},
        request=request,
    )
    await db.commit()
    return {"message": "체크리스트 응답이 저장되었습니다"}


# ============================================================
# T2.3 — Compliance Assessment (no period)
# ============================================================


class AssessIn(BaseModel):
    status: str  # compliant, partial, non_compliant, not_applicable
    notes: str | None = None
    # Optional override. If the caller doesn't send one, the server picks
    # automatically from the user's "current assessment" (see below) as
    # long as the item is in that round's scope.
    assessment_id: int | None = None


@router.post("/items/{code}/assess")
async def assess_item(
    code: str,
    body: AssessIn,
    request: Request,
    current_user: User = Depends(require_role(["cpo", "security_officer"])),
    db: AsyncSession = Depends(get_db),
):
    item = (await db.execute(select(ISMSItem).where(ISMSItem.code == code))).scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="항목을 찾을 수 없습니다")

    # Resolve which assessment this snapshot belongs to.
    # Rules:
    #   1. If the caller passes assessment_id → validate it (must exist,
    #      must not be closed, item must be in scope unless it's the
    #      continuous/상시 flow).
    #   2. If the caller passes nothing → no assessment_id. The client can
    #      send the user's "current assessment" explicitly if they want
    #      auto-attach; the server never guesses from session state.
    from app.models.assessment import Assessment, AssessmentScopeItem, AssessmentStatus

    scope_warning: str | None = None
    if body.assessment_id is not None:
        asmt = (await db.execute(select(Assessment).where(Assessment.id == body.assessment_id))).scalar_one_or_none()
        if not asmt:
            raise HTTPException(status_code=400, detail="평가 세션을 찾을 수 없습니다")
        if asmt.status == AssessmentStatus.closed:
            raise HTTPException(status_code=400, detail="종료된 평가 세션에는 기록할 수 없습니다")
        if asmt.status != AssessmentStatus.active:
            raise HTTPException(
                status_code=400,
                detail="진행 상태가 아닌 평가 세션에는 기록할 수 없습니다 (준비 상태는 '진행 시작'부터)",
            )
        in_scope = (
            await db.execute(
                select(AssessmentScopeItem.id).where(
                    AssessmentScopeItem.assessment_id == body.assessment_id,
                    AssessmentScopeItem.item_id == item.id,
                )
            )
        ).scalar_one_or_none()
        if not in_scope:
            # Don't block — an auditor may legitimately want to record an
            # out-of-scope finding. Surface it as a warning instead, so the
            # UI can ask "add to scope?" before saving.
            scope_warning = f"항목 {code}은 평가 세션 '{asmt.code}'의 범위에 포함되어 있지 않습니다"

    # Auto-aggregate checklist
    cl_total = (
        await db.execute(select(func.count()).select_from(ISMSChecklist).where(ISMSChecklist.item_id == item.id))
    ).scalar()
    cl_checked = (
        await db.execute(
            select(func.count())
            .select_from(ChecklistResponseModel)
            .where(
                ChecklistResponseModel.checklist_id.in_(
                    select(ISMSChecklist.id).where(ISMSChecklist.item_id == item.id)
                ),
                ChecklistResponseModel.is_checked == True,
            )
        )
    ).scalar()

    ev_count = (
        await db.execute(select(func.count()).select_from(EvidenceItemLink).where(EvidenceItemLink.item_id == item.id))
    ).scalar()
    ev_approved = (
        await db.execute(
            select(func.count())
            .select_from(EvidenceItemLink)
            .join(Evidence)
            .where(
                EvidenceItemLink.item_id == item.id,
                Evidence.status == EvidenceStatus.approved,
            )
        )
    ).scalar()

    # Capture checklist states at this moment
    checklists = (
        (
            await db.execute(
                select(ISMSChecklist).where(ISMSChecklist.item_id == item.id).order_by(ISMSChecklist.sort_order)
            )
        )
        .scalars()
        .all()
    )
    cl_snapshot = []
    for cl in checklists:
        resp = (
            await db.execute(
                select(ChecklistResponseModel.is_checked, ChecklistResponseModel.checked_by).where(
                    ChecklistResponseModel.checklist_id == cl.id
                )
            )
        ).one_or_none()
        checker_name = None
        if resp and resp.checked_by:
            checker_name = (await db.execute(select(User.name).where(User.id == resp.checked_by))).scalar()
        cl_snapshot.append(
            {
                "question": cl.question,
                "is_checked": resp.is_checked if resp else False,
                "checked_by": checker_name,
            }
        )

    # Warning for baseless or questionable compliant
    warnings = []
    if body.status == "compliant" and cl_checked == 0 and ev_approved == 0:
        warnings.append("체크리스트 0%, 증적 0건 상태에서 '준수'로 평가됩니다")
    elif body.status == "compliant" and cl_total > 0 and cl_checked < cl_total:
        warnings.append(f"체크리스트 {cl_checked}/{cl_total} 충족 상태에서 '준수'로 평가됩니다 (일부준수 권장)")
    if scope_warning:
        warnings.append(scope_warning)

    # Always insert new snapshot (history accumulates)
    snap = ComplianceSnapshot(
        item_id=item.id,
        assessment_id=body.assessment_id,
        status=ComplianceLevel(body.status),
        checklist_checked=cl_checked,
        checklist_total=cl_total,
        evidence_count=ev_count,
        evidence_approved=ev_approved,
        checklist_snapshot=cl_snapshot,
        notes=body.notes,
        assessed_by=current_user.id,
        assessed_at=datetime.now(UTC),
    )
    db.add(snap)
    await db.flush()
    await log_audit(
        db,
        current_user.id,
        "assess",
        "compliance_snapshot",
        snap.id,
        new_values={
            "item_code": code,
            "status": body.status,
            "checklist": f"{cl_checked}/{cl_total}",
            "evidence_approved": ev_approved,
            "warnings": warnings,
        },
        request=request,
    )
    await db.commit()

    resp = {"message": "준수 상태가 평가되었습니다"}
    if warnings:
        resp["warnings"] = warnings
    return resp


# --- Item compliance history ---
@router.get("/items/{code}/compliance-history")
async def item_compliance_history(
    code: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    item = (await db.execute(select(ISMSItem).where(ISMSItem.code == code))).scalar_one_or_none()
    if not item:
        raise HTTPException(404, "항목을 찾을 수 없습니다")

    result = await db.execute(
        select(ComplianceSnapshot, User.name.label("assessed_by_name"))
        .outerjoin(User, ComplianceSnapshot.assessed_by == User.id)
        .where(ComplianceSnapshot.item_id == item.id)
        .order_by(ComplianceSnapshot.assessed_at.desc())
    )

    snapshots = []
    for row in result:
        snap = row[0]
        checklist_detail = snap.checklist_snapshot or []

        snapshots.append(
            {
                "id": snap.id,
                "status": snap.status.value,
                "checklist_checked": snap.checklist_checked,
                "checklist_total": snap.checklist_total,
                "checklist_detail": checklist_detail,
                "evidence_count": snap.evidence_count,
                "evidence_approved": snap.evidence_approved,
                "prowler_passed": snap.prowler_passed,
                "prowler_failed": snap.prowler_failed,
                "prowler_total": snap.prowler_total,
                "config_compliant": snap.config_compliant,
                "config_non_compliant": snap.config_non_compliant,
                "config_total": snap.config_total,
                "notes": snap.notes,
                "assessed_by_name": row.assessed_by_name,
                "assessed_at": snap.assessed_at.isoformat() if snap.assessed_at else None,
            }
        )

    return snapshots
