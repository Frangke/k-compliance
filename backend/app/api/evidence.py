from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user, require_role
from app.models.evidence import Evidence, EvidenceItemLink, EvidenceStatus, EvidenceType
from app.models.isms import ISMSItem
from app.models.user import User
from app.schemas.evidence import (
    EvidenceResponse,
    EvidenceUpdate,
    ExternalLinkCreate,
    LinkItemsRequest,
    ReviewAction,
)
from app.services.audit import log_audit
from app.services.evidence_service import (
    LOCAL_STORAGE_DIR,
    MAX_FILE_SIZE,
    _use_local,
    compute_sha256,
    generate_download_url,
    upload_to_s3,
    validate_upload_mime,
)

router = APIRouter(prefix="/api/evidence", tags=["evidence"])


# --- Upload ---
@router.post("/upload", response_model=EvidenceResponse, status_code=201)
async def upload_evidence(
    file: UploadFile = File(...),
    title: str = Form(...),
    description: str = Form(None),
    valid_from: date | None = Form(None),
    valid_to: date | None = Form(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Read + validate size first — magic-byte detection needs the content
    data = await file.read()
    if len(data) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="파일 크기가 50MB를 초과합니다")

    # Validate by actual content, not by the client-supplied Content-Type
    real_mime = validate_upload_mime(file.content_type, data)

    # Validate valid_to
    if valid_to and valid_to < date.today():
        raise HTTPException(status_code=400, detail="유효 종료일은 오늘 이후여야 합니다")

    # SHA-256
    file_hash = compute_sha256(data)

    # Create DB record first to get ID
    evidence = Evidence(
        title=title,
        description=description,
        evidence_type=EvidenceType.document,
        file_name=file.filename,
        file_size=len(data),
        mime_type=real_mime,
        file_hash=file_hash,
        valid_from=valid_from,
        valid_to=valid_to,
        uploaded_by=current_user.id,
    )
    db.add(evidence)
    await db.flush()

    # S3 upload
    s3_key = f"evidence/{evidence.id}/{file.filename}"
    await upload_to_s3(data, s3_key, real_mime)
    evidence.file_key = s3_key
    await db.commit()
    await db.refresh(evidence)
    return evidence


# --- External link ---
@router.post("/external-link", response_model=EvidenceResponse, status_code=201)
async def create_external_link(
    body: ExternalLinkCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    evidence = Evidence(
        title=body.title,
        description=body.description,
        evidence_type=EvidenceType.external_link,
        external_url=body.external_url,
        valid_from=body.valid_from,
        valid_to=body.valid_to,
        uploaded_by=current_user.id,
    )
    db.add(evidence)
    await db.commit()
    await db.refresh(evidence)
    return evidence


# --- List / cross-filter search (Evidence Finder) ---
# The single endpoint supports both the simple list view and the auditor-facing
# cross filter ("2.7 items, status=expired, valid_to within a 3-month window").
# status / evidence_type accept comma-separated lists for multi-select UIs.
# item_code_prefix matches ISMSItem.code by LIKE 'prefix%' (e.g. "2.7" hits 2.7.1/2.7.2/...).
@router.get("")
async def list_evidence(
    status: str | None = None,
    evidence_type: str | None = None,
    item_code: str | None = None,
    item_code_prefix: str | None = None,
    search: str | None = None,
    valid_to_from: date | None = None,
    valid_to_to: date | None = None,
    created_from: date | None = None,
    created_to: date | None = None,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    q = select(Evidence)
    count_q = select(func.count()).select_from(Evidence)
    joined_items = False

    def _split(csv: str | None) -> list[str]:
        return [s.strip() for s in csv.split(",") if s.strip()] if csv else []

    status_values = _split(status)
    if status_values:
        q = q.where(Evidence.status.in_(status_values))
        count_q = count_q.where(Evidence.status.in_(status_values))

    type_values = _split(evidence_type)
    if type_values:
        q = q.where(Evidence.evidence_type.in_(type_values))
        count_q = count_q.where(Evidence.evidence_type.in_(type_values))

    if item_code or item_code_prefix:
        q = q.join(EvidenceItemLink).join(ISMSItem)
        count_q = count_q.join(EvidenceItemLink).join(ISMSItem)
        joined_items = True
        if item_code:
            q = q.where(ISMSItem.code == item_code)
            count_q = count_q.where(ISMSItem.code == item_code)
        if item_code_prefix:
            pattern = f"{item_code_prefix}%"
            q = q.where(ISMSItem.code.like(pattern))
            count_q = count_q.where(ISMSItem.code.like(pattern))

    if search:
        like = f"%{search}%"
        q = q.where(Evidence.title.ilike(like))
        count_q = count_q.where(Evidence.title.ilike(like))

    if valid_to_from:
        q = q.where(Evidence.valid_to >= valid_to_from)
        count_q = count_q.where(Evidence.valid_to >= valid_to_from)
    if valid_to_to:
        q = q.where(Evidence.valid_to <= valid_to_to)
        count_q = count_q.where(Evidence.valid_to <= valid_to_to)

    if created_from:
        q = q.where(Evidence.created_at >= created_from)
        count_q = count_q.where(Evidence.created_at >= created_from)
    if created_to:
        q = q.where(Evidence.created_at < created_to)
        count_q = count_q.where(Evidence.created_at < created_to)

    # When we joined evidence_item_links, an evidence row can match multiple
    # items and show up duplicated. Count distinct ids so total matches rows.
    if joined_items:
        q = q.distinct()
        count_q = (
            select(func.count(func.distinct(Evidence.id))).select_from(Evidence).join(EvidenceItemLink).join(ISMSItem)
        )
        # Re-apply every predicate to count_q to keep the counts honest.
        if status_values:
            count_q = count_q.where(Evidence.status.in_(status_values))
        if type_values:
            count_q = count_q.where(Evidence.evidence_type.in_(type_values))
        if item_code:
            count_q = count_q.where(ISMSItem.code == item_code)
        if item_code_prefix:
            count_q = count_q.where(ISMSItem.code.like(f"{item_code_prefix}%"))
        if search:
            count_q = count_q.where(Evidence.title.ilike(f"%{search}%"))
        if valid_to_from:
            count_q = count_q.where(Evidence.valid_to >= valid_to_from)
        if valid_to_to:
            count_q = count_q.where(Evidence.valid_to <= valid_to_to)
        if created_from:
            count_q = count_q.where(Evidence.created_at >= created_from)
        if created_to:
            count_q = count_q.where(Evidence.created_at < created_to)

    total = (await db.execute(count_q)).scalar()
    result = await db.execute(q.order_by(Evidence.id.desc()).offset((page - 1) * size).limit(size))
    evidences = result.scalars().all()

    # Fetch linked item codes for each evidence
    items_out = []
    for ev in evidences:
        linked = await db.execute(
            select(ISMSItem.code).join(EvidenceItemLink).where(EvidenceItemLink.evidence_id == ev.id)
        )
        linked_codes = [r[0] for r in linked]
        ev_dict = EvidenceResponse.model_validate(ev).model_dump()
        ev_dict["linked_items"] = linked_codes
        items_out.append(ev_dict)

    return {"items": items_out, "total": total}


# --- Detail ---
@router.get("/{evidence_id}", response_model=EvidenceResponse)
async def get_evidence(
    evidence_id: int, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    ev = (await db.execute(select(Evidence).where(Evidence.id == evidence_id))).scalar_one_or_none()
    if not ev:
        raise HTTPException(status_code=404, detail="증적을 찾을 수 없습니다")
    return ev


# --- Update (draft/rejected only) ---
@router.put("/{evidence_id}", response_model=EvidenceResponse)
async def update_evidence(
    evidence_id: int,
    body: EvidenceUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ev = (await db.execute(select(Evidence).where(Evidence.id == evidence_id))).scalar_one_or_none()
    if not ev:
        raise HTTPException(status_code=404, detail="증적을 찾을 수 없습니다")
    if ev.status not in (EvidenceStatus.draft, EvidenceStatus.rejected):
        raise HTTPException(status_code=400, detail=f"현재 상태({ev.status.value})에서는 수정할 수 없습니다")

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(ev, field, value)
    # Reset to draft if was rejected
    if ev.status == EvidenceStatus.rejected:
        ev.status = EvidenceStatus.draft
    await db.commit()
    await db.refresh(ev)
    return ev


# --- Submit (draft → submitted) ---
@router.post("/{evidence_id}/submit")
async def submit_evidence(
    evidence_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ev = (await db.execute(select(Evidence).where(Evidence.id == evidence_id))).scalar_one_or_none()
    if not ev:
        raise HTTPException(status_code=404, detail="증적을 찾을 수 없습니다")
    if ev.status != EvidenceStatus.draft:
        raise HTTPException(status_code=400, detail=f"현재 상태({ev.status.value})에서 제출할 수 없습니다")

    ev.status = EvidenceStatus.submitted
    await db.commit()

    # Check for unlinked warning
    link_count = (
        await db.execute(
            select(func.count()).select_from(EvidenceItemLink).where(EvidenceItemLink.evidence_id == evidence_id)
        )
    ).scalar()

    resp = {"message": "증적이 제출되었습니다"}
    if link_count == 0:
        resp["warning"] = "ISMS-P 항목에 연결되지 않은 증적입니다"
    return resp


# --- Review (submitted → approved/rejected) ---
@router.post("/{evidence_id}/review")
async def review_evidence(
    evidence_id: int,
    body: ReviewAction,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ev = (await db.execute(select(Evidence).where(Evidence.id == evidence_id))).scalar_one_or_none()
    if not ev:
        raise HTTPException(status_code=404, detail="증적을 찾을 수 없습니다")
    if ev.status != EvidenceStatus.submitted:
        raise HTTPException(status_code=400, detail=f"현재 상태({ev.status.value})에서 검토할 수 없습니다")

    # Separation of duties (CPO exempt)
    if ev.uploaded_by == current_user.id and current_user.role != "cpo":
        raise HTTPException(status_code=400, detail="본인이 업로드한 증적은 직접 검토할 수 없습니다")

    if body.action == "reject" and not body.comment:
        raise HTTPException(status_code=400, detail="거부 사유를 입력해주세요")

    ev.status = EvidenceStatus.approved if body.action == "approve" else EvidenceStatus.rejected
    ev.reviewed_by = current_user.id
    ev.reviewed_at = datetime.now(UTC)
    ev.review_comment = body.comment

    # Audit log with self_review flag for CPO
    audit_extra = {}
    if ev.uploaded_by == current_user.id:
        audit_extra = {"self_review": True}

    await log_audit(
        db, current_user.id, "UPDATE", "evidence", evidence_id, new_values={"status": ev.status.value, **audit_extra}
    )
    await db.commit()
    return {"message": f"증적이 {'승인' if body.action == 'approve' else '거부'}되었습니다"}


# --- Link items ---
@router.post("/{evidence_id}/link-items")
async def link_items(
    evidence_id: int,
    body: LinkItemsRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ev = (await db.execute(select(Evidence).where(Evidence.id == evidence_id))).scalar_one_or_none()
    if not ev:
        raise HTTPException(status_code=404, detail="증적을 찾을 수 없습니다")

    linked = 0
    for code in body.item_codes:
        item = (await db.execute(select(ISMSItem).where(ISMSItem.code == code))).scalar_one_or_none()
        if not item:
            continue
        existing = (
            await db.execute(
                select(EvidenceItemLink).where(
                    EvidenceItemLink.evidence_id == evidence_id,
                    EvidenceItemLink.item_id == item.id,
                )
            )
        ).scalar_one_or_none()
        if not existing:
            db.add(
                EvidenceItemLink(
                    evidence_id=evidence_id,
                    item_id=item.id,
                    relevance_note=body.relevance_note,
                    linked_by=current_user.id,
                )
            )
            linked += 1

    await db.commit()
    return {"message": f"{linked}개 항목에 연결되었습니다"}


# --- Download ---
@router.get("/{evidence_id}/download")
async def download_evidence(
    evidence_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ev = (await db.execute(select(Evidence).where(Evidence.id == evidence_id))).scalar_one_or_none()
    if not ev or not ev.file_key:
        raise HTTPException(status_code=404, detail="다운로드할 파일이 없습니다")

    await log_audit(db, current_user.id, "DOWNLOAD", "evidence", evidence_id)
    await db.commit()

    url = generate_download_url(ev.file_key)
    return {"download_url": url, "file_name": ev.file_name, "file_hash": ev.file_hash}


# --- Local file serving (when S3 is unavailable) ---
@router.get("/files/{filename}")
async def serve_local_file(filename: str, current_user: User = Depends(get_current_user)):
    if not _use_local:
        raise HTTPException(status_code=404)
    path = LOCAL_STORAGE_DIR / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다")
    return FileResponse(path, filename=filename)


# --- New version ---
@router.post("/{evidence_id}/new-version", response_model=EvidenceResponse, status_code=201)
async def new_version(
    evidence_id: int,
    file: UploadFile = File(...),
    title: str = Form(...),
    description: str = Form(None),
    valid_from: date | None = Form(None),
    valid_to: date | None = Form(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    old = (await db.execute(select(Evidence).where(Evidence.id == evidence_id))).scalar_one_or_none()
    if not old:
        raise HTTPException(status_code=404, detail="증적을 찾을 수 없습니다")

    data = await file.read()
    if len(data) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="파일 크기가 50MB를 초과합니다")

    real_mime = validate_upload_mime(file.content_type, data)

    file_hash = compute_sha256(data)

    # Create new version
    new_ev = Evidence(
        title=title,
        description=description,
        evidence_type=EvidenceType.document,
        file_name=file.filename,
        file_size=len(data),
        mime_type=real_mime,
        file_hash=file_hash,
        valid_from=valid_from,
        valid_to=valid_to,
        version=old.version + 1,
        parent_id=old.id,
        uploaded_by=current_user.id,
    )
    db.add(new_ev)
    await db.flush()

    s3_key = f"evidence/{new_ev.id}/{file.filename}"
    await upload_to_s3(data, s3_key, real_mime)
    new_ev.file_key = s3_key

    # Mark old as replaced
    old.status = EvidenceStatus.replaced

    # Inherit item links
    old_links = (
        (await db.execute(select(EvidenceItemLink).where(EvidenceItemLink.evidence_id == old.id))).scalars().all()
    )
    for link in old_links:
        db.add(
            EvidenceItemLink(
                evidence_id=new_ev.id,
                item_id=link.item_id,
                relevance_note=link.relevance_note,
                linked_by=current_user.id,
            )
        )

    await db.commit()
    await db.refresh(new_ev)
    return new_ev


# --- Versions list ---
@router.get("/{evidence_id}/versions")
async def list_versions(
    evidence_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Walk up to root
    ev = (await db.execute(select(Evidence).where(Evidence.id == evidence_id))).scalar_one_or_none()
    if not ev:
        raise HTTPException(status_code=404, detail="증적을 찾을 수 없습니다")

    root_id = evidence_id
    while ev.parent_id:
        root_id = ev.parent_id
        ev = (await db.execute(select(Evidence).where(Evidence.id == ev.parent_id))).scalar_one_or_none()

    # Find all versions from root
    versions = []
    current = (await db.execute(select(Evidence).where(Evidence.id == root_id))).scalar_one_or_none()
    if current:
        versions.append(EvidenceResponse.model_validate(current))
        # Walk down children
        while True:
            child = (await db.execute(select(Evidence).where(Evidence.parent_id == current.id))).scalar_one_or_none()
            if not child:
                break
            versions.append(EvidenceResponse.model_validate(child))
            current = child

    return {"versions": versions}


# --- Export ---
@router.post("/export", status_code=201)
async def export_evidence(
    status_filter: str = Query("approved"),
    include_checklists: bool = Query(True),
    current_user: User = Depends(require_role(["cpo", "security_officer", "auditor"])),
    db: AsyncSession = Depends(get_db),
):
    import asyncio

    from app.models.export import ExportJob
    from app.services.export_service import export_evidence_package

    job = ExportJob(
        options={"status_filter": status_filter, "include_checklists": include_checklists},
        triggered_by=current_user.id,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    asyncio.create_task(export_evidence_package(db, job))
    return {"job_id": job.id, "message": "내보내기가 시작되었습니다"}


@router.get("/export/{job_id}")
async def get_export_job(
    job_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.models.export import ExportJob
    from app.services.evidence_service import generate_download_url

    job = (await db.execute(select(ExportJob).where(ExportJob.id == job_id))).scalar_one_or_none()
    if not job:
        raise HTTPException(404, "내보내기 작업을 찾을 수 없습니다")

    result = {
        "id": job.id,
        "status": job.status.value,
        "total_items": job.total_items,
        "processed_items": job.processed_items,
        "file_size": job.file_size,
    }
    if job.file_key:
        result["download_url"] = generate_download_url(job.file_key, expires=3600)
    if job.error_message:
        result["error"] = job.error_message
    return result
