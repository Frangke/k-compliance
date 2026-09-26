import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user, require_role
from app.models.aws_config import ConfigEvaluation, ConfigSyncJob
from app.models.prowler import CloudAccount, ScanStatus
from app.models.user import User
from app.services.audit import log_audit
from app.services.aws_config_service import sync_conformance_pack

router = APIRouter(prefix="/api/config", tags=["aws-config"])


@router.get("/sync-jobs")
async def list_sync_jobs(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(
            ConfigSyncJob, CloudAccount.alias.label("account_alias"), CloudAccount.account_id.label("account_number")
        )
        .outerjoin(CloudAccount, ConfigSyncJob.cloud_account_id == CloudAccount.id)
        .order_by(ConfigSyncJob.id.desc())
    )
    return [
        {
            "id": j.id,
            "conformance_pack": j.conformance_pack,
            "status": j.status.value,
            "total_rules": j.total_rules,
            "compliant": j.compliant,
            "non_compliant": j.non_compliant,
            "error_message": j.error_message,
            "started_at": j.started_at.isoformat() if j.started_at else None,
            "completed_at": j.completed_at.isoformat() if j.completed_at else None,
            "cloud_account_alias": account_alias,
            "cloud_account_id": account_number,
        }
        for j, account_alias, account_number in result.all()
    ]


@router.post("/sync", status_code=201)
async def sync_config(
    request: Request,
    cloud_account_id: int | None = Query(None),
    conformance_pack: str = Query("Operational-Best-Practices-for-K-ISMS"),
    current_user: User = Depends(require_role(["cpo", "security_officer"])),
    db: AsyncSession = Depends(get_db),
):
    # Validate cloud account if specified
    if cloud_account_id:
        acc = (await db.execute(select(CloudAccount).where(CloudAccount.id == cloud_account_id))).scalar_one_or_none()
        if not acc or not acc.is_active:
            raise HTTPException(400, "유효하지 않은 클라우드 계정입니다")

    job = ConfigSyncJob(
        triggered_by=current_user.id,
        cloud_account_id=cloud_account_id,
        conformance_pack=conformance_pack,
    )
    db.add(job)
    await db.flush()
    await log_audit(
        db,
        current_user.id,
        "sync.start",
        "config_sync_job",
        job.id,
        new_values={"cloud_account_id": cloud_account_id, "conformance_pack": conformance_pack},
        request=request,
    )
    await db.commit()
    await db.refresh(job)

    # Run in background with its own AsyncSession (P0-2 fix). Poll the job
    # status via GET /api/config/sync-jobs/{id} to see when it completes.
    job_id = job.id
    asyncio.create_task(sync_conformance_pack(job_id))

    return {"id": job_id, "message": "Config 동기화가 시작되었습니다"}


@router.get("/sync-jobs/{job_id}")
async def get_sync_job(job_id: int, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    job = (await db.execute(select(ConfigSyncJob).where(ConfigSyncJob.id == job_id))).scalar_one_or_none()
    if not job:
        raise HTTPException(404, "동기화 작업을 찾을 수 없습니다")
    return {
        "id": job.id,
        "status": job.status.value,
        "total_rules": job.total_rules,
        "compliant": job.compliant,
        "non_compliant": job.non_compliant,
    }


@router.get("/evaluations")
async def list_evaluations(
    compliance_type: str | None = None,
    isms_item_id: int | None = None,
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    q = select(ConfigEvaluation)
    count_q = select(func.count()).select_from(ConfigEvaluation)
    if compliance_type:
        q = q.where(ConfigEvaluation.compliance_type == compliance_type)
        count_q = count_q.where(ConfigEvaluation.compliance_type == compliance_type)
    if isms_item_id:
        q = q.where(ConfigEvaluation.isms_item_id == isms_item_id)
        count_q = count_q.where(ConfigEvaluation.isms_item_id == isms_item_id)

    total = (await db.execute(count_q)).scalar()
    result = await db.execute(q.order_by(ConfigEvaluation.id.desc()).offset((page - 1) * size).limit(size))
    return {
        "items": [
            {
                "id": e.id,
                "config_rule_name": e.config_rule_name,
                "compliance_type": e.compliance_type,
                "resource_type": e.resource_type,
                "resource_id": e.resource_id,
                "isms_item_id": e.isms_item_id,
                "remediation_status": e.remediation_status.value,
            }
            for e in result.scalars()
        ],
        "total": total,
    }


@router.put("/evaluations/{eval_id}/remediate")
async def remediate_evaluation(
    eval_id: int,
    request: Request,
    remediation_status: str = Query(...),
    notes: str | None = None,
    current_user: User = Depends(require_role(["cpo", "security_officer"])),
    db: AsyncSession = Depends(get_db),
):
    ev = (await db.execute(select(ConfigEvaluation).where(ConfigEvaluation.id == eval_id))).scalar_one_or_none()
    if not ev:
        raise HTTPException(404, "평가 결과를 찾을 수 없습니다")
    ev.remediation_status = remediation_status
    ev.remediation_notes = notes
    await log_audit(
        db,
        current_user.id,
        "remediate",
        "config_evaluation",
        eval_id,
        new_values={"remediation_status": remediation_status},
        request=request,
    )
    await db.commit()
    return {"message": "조치 상태가 업데이트되었습니다"}


@router.get("/summary")
async def config_summary(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    # Latest sync job
    latest = (
        await db.execute(
            select(ConfigSyncJob).where(ConfigSyncJob.status == ScanStatus.completed).order_by(ConfigSyncJob.id.desc())
        )
    ).scalar_one_or_none()
    if not latest:
        return {"message": "아직 동기화가 수행되지 않았습니다", "total_rules": 0}

    pending = (
        await db.execute(
            select(func.count())
            .select_from(ConfigEvaluation)
            .where(
                ConfigEvaluation.sync_job_id == latest.id,
                ConfigEvaluation.compliance_type == "NON_COMPLIANT",
                ConfigEvaluation.remediation_status == "open",
            )
        )
    ).scalar()

    return {
        "sync_job_id": latest.id,
        "total_rules": latest.total_rules,
        "compliant": latest.compliant,
        "non_compliant": latest.non_compliant,
        "remediation_pending": pending,
        "synced_at": latest.completed_at.isoformat() if latest.completed_at else None,
    }
