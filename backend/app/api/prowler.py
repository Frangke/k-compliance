import asyncio
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user, require_role
from app.models.prowler import CloudAccount, ProwlerFinding, ScanJob, ScanProvider, ScanStatus
from app.models.user import User
from app.schemas.cloud_account import (
    CloudAccountCreate,
    CloudAccountUpdate,
)
from app.services.audit import log_audit
from app.services.aws_session import verify_aws_access
from app.services.crypto import decrypt_json, encrypt_json
from app.services.prowler_service import start_scan

router = APIRouter(prefix="/api/prowler", tags=["prowler"])


def _serialize_account(a: CloudAccount) -> dict:
    cred: dict = {}
    if a.credentials:
        try:
            cred = decrypt_json(a.credentials)
        except Exception:
            cred = {}
    return {
        "id": a.id,
        "provider": a.provider.value,
        "account_id": a.account_id,
        "alias": a.alias,
        "purpose": a.purpose,
        "admin_name": a.admin_name,
        "admin_email": a.admin_email,
        "is_active": a.is_active,
        "auth_type": a.auth_type or "instance_role",
        "role_arn": cred.get("role_arn"),
        "external_id": cred.get("external_id"),
        "default_region": a.default_region,
        "credentials_last_updated": a.credentials_last_updated.isoformat() if a.credentials_last_updated else None,
    }


# --- Cloud accounts ---
@router.get("/cloud-accounts")
async def list_accounts(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(CloudAccount).order_by(CloudAccount.id))
    return [_serialize_account(a) for a in result.scalars()]


@router.post("/cloud-accounts", status_code=201)
async def create_account(
    body: CloudAccountCreate,
    request: Request,
    current_user: User = Depends(require_role(["cpo", "security_officer"])),
    db: AsyncSession = Depends(get_db),
):
    # Reject duplicates
    existing = (
        await db.execute(
            select(CloudAccount).where(
                CloudAccount.provider == ScanProvider(body.provider), CloudAccount.account_id == body.account_id
            )
        )
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(400, "이미 등록된 계정입니다")

    acc = CloudAccount(
        provider=ScanProvider(body.provider),
        account_id=body.account_id,
        alias=body.alias,
        purpose=body.purpose,
        admin_name=body.admin_name,
        admin_email=body.admin_email,
        auth_type=body.auth_type,
        default_region=body.default_region,
    )

    if body.auth_type == "assume_role":
        acc.credentials = encrypt_json(
            {
                "role_arn": body.role_arn,
                "external_id": body.external_id,
            }
        )
        acc.credentials_last_updated = datetime.now(UTC)
    else:
        acc.credentials = None

    db.add(acc)
    await db.flush()
    await log_audit(
        db,
        current_user.id,
        "create",
        "cloud_account",
        acc.id,
        new_values={
            "provider": body.provider,
            "account_id": body.account_id,
            "alias": body.alias,
            "auth_type": body.auth_type,
            "default_region": body.default_region,
            "credentials_set": body.auth_type == "assume_role",
        },
        request=request,
    )
    await db.commit()
    await db.refresh(acc)
    return {"id": acc.id, "message": "클라우드 계정이 등록되었습니다", "account": _serialize_account(acc)}


@router.put("/cloud-accounts/{account_id}")
async def update_account(
    account_id: int,
    body: CloudAccountUpdate,
    request: Request,
    current_user: User = Depends(require_role(["cpo", "security_officer"])),
    db: AsyncSession = Depends(get_db),
):
    acc = (await db.execute(select(CloudAccount).where(CloudAccount.id == account_id))).scalar_one_or_none()
    if not acc:
        raise HTTPException(404, "계정을 찾을 수 없습니다")

    if body.alias is not None:
        acc.alias = body.alias
    if body.purpose is not None:
        acc.purpose = body.purpose
    if body.admin_name is not None:
        acc.admin_name = body.admin_name
    if body.admin_email is not None:
        acc.admin_email = body.admin_email
    if body.is_active is not None:
        acc.is_active = body.is_active
    if body.default_region is not None:
        acc.default_region = body.default_region

    # Credential update
    if body.auth_type is not None:
        acc.auth_type = body.auth_type
        if body.auth_type == "instance_role":
            acc.credentials = None
            acc.credentials_last_updated = datetime.now(UTC)
        elif body.auth_type == "assume_role":
            if not body.role_arn or not body.role_arn.startswith("arn:aws:iam::"):
                raise HTTPException(400, "assume_role에는 유효한 role_arn이 필요합니다")
            acc.credentials = encrypt_json(
                {
                    "role_arn": body.role_arn,
                    "external_id": body.external_id,
                }
            )
            acc.credentials_last_updated = datetime.now(UTC)
    elif body.role_arn is not None or body.external_id is not None:
        # Updating ARN/ExternalId without changing type — must already be assume_role
        if acc.auth_type != "assume_role":
            raise HTTPException(400, "role_arn/external_id 수정은 auth_type=assume_role 에서만 가능합니다")
        current = {}
        if acc.credentials:
            try:
                current = decrypt_json(acc.credentials)
            except Exception:
                current = {}
        if body.role_arn is not None:
            current["role_arn"] = body.role_arn
        if body.external_id is not None:
            current["external_id"] = body.external_id
        acc.credentials = encrypt_json(current)
        acc.credentials_last_updated = datetime.now(UTC)

    update_fields = {
        k: v for k, v in body.model_dump(exclude_unset=True).items() if k not in ("role_arn", "external_id")
    }
    update_fields["credentials_changed"] = (
        body.auth_type is not None or body.role_arn is not None or body.external_id is not None
    )
    await log_audit(db, current_user.id, "update", "cloud_account", acc.id, new_values=update_fields, request=request)
    await db.commit()
    await db.refresh(acc)
    return {"message": "계정이 수정되었습니다", "account": _serialize_account(acc)}


@router.post("/cloud-accounts/{account_id}/verify")
async def verify_account(
    account_id: int,
    request: Request,
    current_user: User = Depends(require_role(["cpo", "security_officer"])),
    db: AsyncSession = Depends(get_db),
):
    """Call STS GetCallerIdentity to verify the configured credentials work."""
    acc = (await db.execute(select(CloudAccount).where(CloudAccount.id == account_id))).scalar_one_or_none()
    if not acc:
        raise HTTPException(404, "계정을 찾을 수 없습니다")

    cred: dict = {}
    if acc.credentials:
        try:
            cred = decrypt_json(acc.credentials)
        except Exception:
            raise HTTPException(500, "자격증명 복호화 실패 (ENCRYPTION_KEY 변경 가능성)")

    result = verify_aws_access(
        auth_type=acc.auth_type,
        region=acc.default_region,
        role_arn=cred.get("role_arn"),
        external_id=cred.get("external_id"),
        expected_account_id=acc.account_id,
    )
    await log_audit(
        db,
        current_user.id,
        "verify",
        "cloud_account",
        account_id,
        new_values={"ok": result.get("ok"), "account_id": acc.account_id},
        request=request,
    )
    await db.commit()
    return result


@router.delete("/cloud-accounts/{account_id}")
async def delete_account(
    account_id: int,
    request: Request,
    current_user: User = Depends(require_role(["cpo"])),
    db: AsyncSession = Depends(get_db),
):
    acc = (await db.execute(select(CloudAccount).where(CloudAccount.id == account_id))).scalar_one_or_none()
    if not acc:
        raise HTTPException(404, "계정을 찾을 수 없습니다")
    old_values = {"provider": acc.provider.value, "account_id": acc.account_id, "alias": acc.alias}
    await db.delete(acc)
    await log_audit(db, current_user.id, "delete", "cloud_account", account_id, old_values=old_values, request=request)
    await db.commit()
    return {"message": "계정이 삭제되었습니다"}


# --- Scans ---
@router.get("/scans")
async def list_scans(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    total = (await db.execute(select(func.count()).select_from(ScanJob))).scalar()
    result = await db.execute(
        select(ScanJob, CloudAccount.alias.label("account_alias"), CloudAccount.account_id.label("account_number"))
        .outerjoin(CloudAccount, ScanJob.cloud_account_id == CloudAccount.id)
        .order_by(ScanJob.id.desc())
        .offset((page - 1) * size)
        .limit(size)
    )
    items = []
    for row in result:
        s = row[0]
        items.append(
            {
                "id": s.id,
                "provider": s.provider.value,
                "compliance": s.compliance,
                "status": s.status.value,
                "total_checks": s.total_checks,
                "passed": s.passed,
                "failed": s.failed,
                "started_at": s.started_at.isoformat() if s.started_at else None,
                "completed_at": s.completed_at.isoformat() if s.completed_at else None,
                "error_message": s.error_message,
                "cloud_account_alias": row.account_alias,
                "cloud_account_id": row.account_number,
            }
        )
    return {"items": items, "total": total}


@router.post("/scans", status_code=201)
async def create_scan(
    request: Request,
    cloud_account_id: int | None = None,
    current_user: User = Depends(require_role(["cpo", "security_officer"])),
    db: AsyncSession = Depends(get_db),
):
    # Check no running scan
    running = (
        await db.execute(select(func.count()).select_from(ScanJob).where(ScanJob.status.in_(["pending", "running"])))
    ).scalar()
    if running > 0:
        raise HTTPException(409, "이미 진행 중인 스캔이 있습니다")

    # Validate cloud account if specified
    if cloud_account_id:
        acc = (await db.execute(select(CloudAccount).where(CloudAccount.id == cloud_account_id))).scalar_one_or_none()
        if not acc or not acc.is_active:
            raise HTTPException(400, "유효하지 않은 클라우드 계정입니다")

    scan = ScanJob(cloud_account_id=cloud_account_id, triggered_by=current_user.id)
    db.add(scan)
    await db.flush()
    await log_audit(
        db,
        current_user.id,
        "scan.start",
        "scan_job",
        scan.id,
        new_values={"cloud_account_id": cloud_account_id},
        request=request,
    )
    await db.commit()
    await db.refresh(scan)

    # Run in background with its own AsyncSession (P0-2 fix).
    # Never pass the request-scoped `db` into a create_task — FastAPI closes it
    # as soon as this handler returns.
    scan_id = scan.id
    asyncio.create_task(start_scan(scan_id))

    return {"id": scan_id, "message": "스캔이 시작되었습니다"}


@router.get("/scans/{scan_id}")
async def get_scan(scan_id: int, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    scan = (await db.execute(select(ScanJob).where(ScanJob.id == scan_id))).scalar_one_or_none()
    if not scan:
        raise HTTPException(404, "스캔을 찾을 수 없습니다")
    return {
        "id": scan.id,
        "status": scan.status.value,
        "compliance": scan.compliance,
        "total_checks": scan.total_checks,
        "passed": scan.passed,
        "failed": scan.failed,
        "started_at": scan.started_at.isoformat() if scan.started_at else None,
        "completed_at": scan.completed_at.isoformat() if scan.completed_at else None,
        "error_message": scan.error_message,
    }


@router.get("/scans/{scan_id}/findings")
async def list_findings(
    scan_id: int,
    status: str | None = None,
    severity: str | None = None,
    isms_item_id: int | None = None,
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    q = select(ProwlerFinding).where(ProwlerFinding.scan_job_id == scan_id)
    count_q = select(func.count()).select_from(ProwlerFinding).where(ProwlerFinding.scan_job_id == scan_id)

    if status:
        q = q.where(ProwlerFinding.status == status)
        count_q = count_q.where(ProwlerFinding.status == status)
    if severity:
        q = q.where(ProwlerFinding.severity == severity)
        count_q = count_q.where(ProwlerFinding.severity == severity)
    if isms_item_id:
        q = q.where(ProwlerFinding.isms_item_id == isms_item_id)
        count_q = count_q.where(ProwlerFinding.isms_item_id == isms_item_id)

    total = (await db.execute(count_q)).scalar()
    result = await db.execute(q.order_by(ProwlerFinding.id).offset((page - 1) * size).limit(size))
    return {
        "items": [
            {
                "id": f.id,
                "check_id": f.check_id,
                "check_title": f.check_title,
                "status": f.status.value,
                "severity": f.severity.value,
                "resource_uid": f.resource_uid,
                "resource_type": f.resource_type,
                "resource_region": f.resource_region,
                "isms_item_id": f.isms_item_id,
                "remediation_status": f.remediation_status.value,
            }
            for f in result.scalars()
        ],
        "total": total,
    }


@router.post("/scans/{scan_id}/cancel")
async def cancel_scan(
    scan_id: int,
    request: Request,
    current_user: User = Depends(require_role(["cpo", "security_officer"])),
    db: AsyncSession = Depends(get_db),
):
    scan = (await db.execute(select(ScanJob).where(ScanJob.id == scan_id))).scalar_one_or_none()
    if not scan:
        raise HTTPException(404, "스캔을 찾을 수 없습니다")
    if scan.status not in (ScanStatus.pending, ScanStatus.running):
        raise HTTPException(400, "취소할 수 없는 상태입니다")
    scan.status = ScanStatus.cancelled
    scan.completed_at = datetime.now(UTC)
    await log_audit(db, current_user.id, "scan.cancel", "scan_job", scan_id, request=request)
    await db.commit()
    return {"message": "스캔이 취소되었습니다"}


@router.put("/findings/{finding_id}/remediate")
async def remediate_finding(
    finding_id: int,
    request: Request,
    remediation_status: str = Query(...),
    notes: str | None = None,
    current_user: User = Depends(require_role(["cpo", "security_officer"])),
    db: AsyncSession = Depends(get_db),
):
    f = (await db.execute(select(ProwlerFinding).where(ProwlerFinding.id == finding_id))).scalar_one_or_none()
    if not f:
        raise HTTPException(404, "발견사항을 찾을 수 없습니다")
    f.remediation_status = remediation_status
    f.remediation_notes = notes
    f.remediated_by = current_user.id
    f.remediated_at = datetime.now(UTC)
    await log_audit(
        db,
        current_user.id,
        "remediate",
        "prowler_finding",
        finding_id,
        new_values={"remediation_status": remediation_status},
        request=request,
    )
    await db.commit()
    return {"message": "조치 상태가 업데이트되었습니다"}
