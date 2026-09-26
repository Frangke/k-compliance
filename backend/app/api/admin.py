from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.dependencies import require_role
from app.models.audit import AuditLog
from app.models.user import User
from app.services.sample_data import generate_sample_data

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.post("/reset-data")
async def reset_data(
    request: Request,
    current_user: User = Depends(require_role(["cpo"])),
    db: AsyncSession = Depends(get_db),
):
    """개발환경 전용: 운영 데이터를 초기화하고 시드 데이터(ISMS-P 항목, 체크리스트)만 유지."""
    if settings.APP_ENV != "development":
        raise HTTPException(status_code=403, detail="이 기능은 개발환경(APP_ENV=development)에서만 사용 가능합니다")

    # Order matters — FK constraints
    tables_to_truncate = [
        # Compliance & assessments
        "compliance_snapshots",
        "checklist_responses",
        # Evidence
        "evidence_item_links",
        "evidence",
        # PIPA
        "incident_timelines",
        "incidents",
        "consent_versions",
        "consent_templates",
        "dsr_requests",
        "destruction_records",
        "third_party_processors",
        # Corrective actions
        "corrective_actions",
        # Prowler & Config
        "prowler_findings",
        "scan_jobs",
        "config_evaluations",
        "config_sync_jobs",
        # Notifications & audit
        "notifications",
        "audit_logs",
        # Auth tokens (not users)
        "refresh_tokens",
        "password_history",
        # Assignments
        "isms_item_assignments",
    ]

    # Get existing tables first
    existing = await db.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'"))
    existing_tables = {row[0] for row in existing.all()}

    # Get row counts before truncation
    truncated = []
    for table in tables_to_truncate:
        if table not in existing_tables:
            continue
        result = await db.execute(text(f"SELECT COUNT(*) FROM {table}"))
        count = result.scalar()
        if count and count > 0:
            truncated.append({"table": table, "deleted": count})

    # Truncate all at once (faster, handles FK)
    tables_to_clear = [t["table"] for t in truncated]
    if tables_to_clear:
        await db.execute(text(f"TRUNCATE TABLE {', '.join(tables_to_clear)} RESTART IDENTITY CASCADE"))

    # Reset user login state (keep users)
    await db.execute(text("UPDATE users SET failed_login_count = 0, locked_until = NULL"))

    # Log the reset itself into the freshly-truncated audit_logs so the event persists.
    # We add this AFTER the TRUNCATE so it survives; we do it inline rather than via
    # log_audit() to avoid re-reading request metadata after the transaction reset.
    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent", "")[:500]
    db.add(
        AuditLog(
            user_id=current_user.id,
            action="admin.reset_data",
            entity_type="system",
            new_values={
                "truncated_tables": [t["table"] for t in truncated],
                "total_rows_deleted": sum(t["deleted"] for t in truncated),
            },
            ip_address=ip,
            user_agent=ua,
        )
    )
    await db.commit()

    return {
        "message": "데이터가 초기화되었습니다",
        "truncated": truncated,
        "preserved": ["users", "isms_domains", "isms_subdomains", "isms_items", "isms_checklists", "cloud_accounts"],
    }


@router.post("/generate-sample-data")
async def generate_sample(
    request: Request,
    current_user: User = Depends(require_role(["cpo"])),
    db: AsyncSession = Depends(get_db),
):
    """개발환경 전용: ISMS-P 데모용 샘플 데이터 생성 (평가, 증적, 시정조치)."""
    if settings.APP_ENV != "development":
        raise HTTPException(status_code=403, detail="이 기능은 개발환경(APP_ENV=development)에서만 사용 가능합니다")

    stats = await generate_sample_data(db, current_user)
    if "error" in stats:
        raise HTTPException(status_code=400, detail=stats["error"])

    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent", "")[:500]
    db.add(
        AuditLog(
            user_id=current_user.id,
            action="admin.generate_sample_data",
            entity_type="system",
            new_values={"stats": stats},
            ip_address=ip,
            user_agent=ua,
        )
    )
    await db.commit()

    return {
        "message": "샘플 데이터가 생성되었습니다",
        "stats": stats,
    }
