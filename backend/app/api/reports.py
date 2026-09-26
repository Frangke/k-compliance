"""Report generation and management API — SPEC 4.10 / 9.x.

P0-3: report generation is asynchronous. POST endpoints return immediately
with job_id + status=generating. The frontend polls GET /api/reports to
observe the status transition to `completed` (or `failed` with an
`error_message`).
"""

import asyncio
from datetime import date

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user, require_role
from app.models.report import GeneratedReport, ReportStatus, ReportType
from app.models.user import User
from app.services.audit import log_audit
from app.services.report_service import (
    get_report_path,
    prepare_report,
    run_corrective_action_report,
    run_dashboard_snapshot,
    run_evidence_package,
    run_isms_assessment,
)

router = APIRouter(prefix="/api/reports", tags=["reports"])


class EvidenceCurationBody(BaseModel):
    """Optional body for evidence-package curation (P1-4).

    - `include_evidence_ids` non-empty → use exactly those IDs; status/domain
      query params are ignored for row selection.
    - `exclude_evidence_ids` → subtract from the final set (always applied).
    Leave both empty to keep the legacy bulk-by-filter behavior.
    """

    include_evidence_ids: list[int] | None = None
    exclude_evidence_ids: list[int] | None = None


@router.post("/isms-assessment")
async def create_isms_assessment(
    request: Request,
    period_start: date = Query(..., description="시작일 (예: 2026-01-01)"),
    period_end: date = Query(..., description="종료일 (예: 2026-03-31)"),
    assessment_id: int | None = Query(None, description="평가 세션 ID (선택)"),
    current_user: User = Depends(require_role(["cpo", "security_officer"])),
    db: AsyncSession = Depends(get_db),
):
    """Schedule an ISMS-P assessment report. Returns job_id immediately."""
    if period_start > period_end:
        raise HTTPException(status_code=400, detail="시작일이 종료일보다 늦을 수 없습니다")

    report = await prepare_report(
        db,
        ReportType.isms_assessment,
        title=f"ISMS-P 인증 심사 대응 보고서 ({period_start} ~ {period_end})",
        period_start=period_start,
        period_end=period_end,
        user_id=current_user.id,
        assessment_id=assessment_id,
    )
    await log_audit(
        db,
        current_user.id,
        "report.generate",
        "generated_reports",
        report.id,
        new_values={
            "type": "isms_assessment",
            "period_start": str(period_start),
            "period_end": str(period_end),
            "title": report.title,
            "assessment_id": assessment_id,
        },
        request=request,
    )
    await db.commit()
    await db.refresh(report)

    asyncio.create_task(run_isms_assessment(report.id))
    return _report_dict(report)


@router.post("/corrective-action")
async def create_corrective_action_report(
    request: Request,
    period_start: date = Query(..., description="시작일"),
    period_end: date = Query(..., description="종료일"),
    current_user: User = Depends(require_role(["cpo", "security_officer"])),
    db: AsyncSession = Depends(get_db),
):
    """Schedule a corrective-action report (HTML + CSV). Returns job_id immediately."""
    if period_start > period_end:
        raise HTTPException(status_code=400, detail="시작일이 종료일보다 늦을 수 없습니다")
    report = await prepare_report(
        db,
        ReportType.corrective_action,
        title=f"시정조치 보고서 ({period_start} ~ {period_end})",
        period_start=period_start,
        period_end=period_end,
        user_id=current_user.id,
    )
    await log_audit(
        db,
        current_user.id,
        "report.generate",
        "generated_reports",
        report.id,
        new_values={"type": "corrective_action", "period": f"{period_start}~{period_end}"},
        request=request,
    )
    await db.commit()
    await db.refresh(report)

    asyncio.create_task(run_corrective_action_report(report.id))
    return _report_dict(report)


@router.post("/evidence-package")
async def create_evidence_package(
    request: Request,
    period_start: date = Query(..., description="시작일"),
    period_end: date = Query(..., description="종료일"),
    domain: str | None = Query(None, description="도메인 코드 필터 (1/2/3)"),
    status_filter: str = Query("approved", description="증적 상태 필터"),
    curation: EvidenceCurationBody | None = Body(None),
    current_user: User = Depends(require_role(["cpo", "security_officer"])),
    db: AsyncSession = Depends(get_db),
):
    """Schedule an evidence-package ZIP build. Returns job_id immediately.

    For the curated flow (P1-4), pass a body with `include_evidence_ids`
    and/or `exclude_evidence_ids`. When include is non-empty, status/domain
    query params are no longer used for selection.
    """
    if period_start > period_end:
        raise HTTPException(status_code=400, detail="시작일이 종료일보다 늦을 수 없습니다")

    include_ids = curation.include_evidence_ids if curation else None
    exclude_ids = curation.exclude_evidence_ids if curation else None

    report = await prepare_report(
        db,
        ReportType.evidence_package,
        title=f"증적 패키지 ({period_start} ~ {period_end})",
        period_start=period_start,
        period_end=period_end,
        user_id=current_user.id,
    )
    audit_values: dict = {
        "type": "evidence_package",
        "period": f"{period_start}~{period_end}",
        "domain": domain,
        "status_filter": status_filter,
    }
    if include_ids:
        audit_values["include_evidence_ids"] = include_ids
    if exclude_ids:
        audit_values["exclude_evidence_ids"] = exclude_ids
    await log_audit(
        db, current_user.id, "report.generate", "generated_reports", report.id, new_values=audit_values, request=request
    )
    await db.commit()
    await db.refresh(report)

    asyncio.create_task(
        run_evidence_package(
            report.id,
            domain_filter=domain,
            status_filter=status_filter,
            include_evidence_ids=include_ids,
            exclude_evidence_ids=exclude_ids,
        )
    )
    return _report_dict(report)


@router.post("/dashboard-snapshot")
async def create_dashboard_snapshot(
    request: Request,
    current_user: User = Depends(require_role(["cpo", "security_officer"])),
    db: AsyncSession = Depends(get_db),
):
    """Schedule a dashboard snapshot HTML build. Returns job_id immediately."""
    today = date.today()
    report = await prepare_report(
        db,
        ReportType.dashboard_snapshot,
        title=f"대시보드 스냅샷 ({today})",
        period_start=today,
        period_end=today,
        user_id=current_user.id,
    )
    await log_audit(
        db,
        current_user.id,
        "report.generate",
        "generated_reports",
        report.id,
        new_values={"type": "dashboard_snapshot"},
        request=request,
    )
    await db.commit()
    await db.refresh(report)

    asyncio.create_task(run_dashboard_snapshot(report.id))
    return _report_dict(report)


@router.get("")
async def list_reports(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all generated reports."""
    result = await db.execute(select(GeneratedReport).order_by(desc(GeneratedReport.generated_at)))
    reports = result.scalars().all()
    return [_report_dict(r) for r in reports]


@router.get("/{report_id}/html")
async def get_report_html(
    report_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get report HTML content for preview/download."""
    report = (await db.execute(select(GeneratedReport).where(GeneratedReport.id == report_id))).scalar_one_or_none()

    if not report:
        raise HTTPException(status_code=404, detail="보고서를 찾을 수 없습니다")
    if report.status != ReportStatus.completed:
        raise HTTPException(status_code=400, detail="보고서가 아직 생성 중이거나 실패했습니다")

    path = get_report_path(report.file_key)
    if not path:
        raise HTTPException(status_code=404, detail="보고서 파일을 찾을 수 없습니다")

    html = path.read_text(encoding="utf-8")
    return HTMLResponse(content=html)


@router.get("/{report_id}/csv")
async def get_report_csv(
    report_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Download CSV sibling for corrective-action report (only applicable type)."""
    report = (await db.execute(select(GeneratedReport).where(GeneratedReport.id == report_id))).scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="보고서를 찾을 수 없습니다")
    if report.report_type != ReportType.corrective_action:
        raise HTTPException(status_code=400, detail="CSV는 시정조치 보고서에서만 제공됩니다")
    if not report.file_key:
        raise HTTPException(status_code=404, detail="보고서 파일이 없습니다")
    csv_key = report.file_key.replace(".html", ".csv")
    path = get_report_path(csv_key)
    if not path:
        raise HTTPException(status_code=404, detail="CSV 파일을 찾을 수 없습니다")
    return FileResponse(path, media_type="text/csv", filename=path.name)


@router.get("/{report_id}/download")
async def download_report_file(
    report_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Download raw report file (HTML/ZIP)."""
    report = (await db.execute(select(GeneratedReport).where(GeneratedReport.id == report_id))).scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="보고서를 찾을 수 없습니다")
    if report.status != ReportStatus.completed or not report.file_key:
        raise HTTPException(status_code=400, detail="보고서가 준비되지 않았습니다")
    path = get_report_path(report.file_key)
    if not path:
        raise HTTPException(status_code=404, detail="보고서 파일을 찾을 수 없습니다")
    media = "application/zip" if path.suffix == ".zip" else "text/html"
    return FileResponse(path, media_type=media, filename=path.name)


@router.delete("/{report_id}")
async def delete_report(
    report_id: int,
    request: Request,
    current_user: User = Depends(require_role(["cpo", "security_officer"])),
    db: AsyncSession = Depends(get_db),
):
    """Delete a generated report + sibling files (CSV if any)."""
    report = (await db.execute(select(GeneratedReport).where(GeneratedReport.id == report_id))).scalar_one_or_none()

    if not report:
        raise HTTPException(status_code=404, detail="보고서를 찾을 수 없습니다")

    if report.file_key:
        path = get_report_path(report.file_key)
        if path:
            path.unlink(missing_ok=True)
        csv_key = report.file_key.replace(".html", ".csv")
        csv_path = get_report_path(csv_key)
        if csv_path:
            csv_path.unlink(missing_ok=True)

    await log_audit(
        db,
        current_user.id,
        "report.delete",
        "generated_reports",
        report.id,
        old_values={"title": report.title, "report_type": report.report_type.value},
        request=request,
    )
    await db.delete(report)
    await db.commit()
    return {"message": "보고서가 삭제되었습니다"}


def _report_dict(report: GeneratedReport) -> dict:
    return {
        "id": report.id,
        "report_code": report.report_code,
        "report_type": report.report_type.value,
        "title": report.title,
        "period_start": str(report.period_start),
        "period_end": str(report.period_end),
        "status": report.status.value,
        "file_key": report.file_key,
        "file_size": report.file_size,
        "error_message": report.error_message,
        "assessment_id": report.assessment_id,
        "generated_by": report.generated_by,
        "generated_at": report.generated_at.isoformat() if report.generated_at else None,
    }
