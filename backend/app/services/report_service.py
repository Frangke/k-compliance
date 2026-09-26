"""Report generation service — ISMS assessment / corrective action / evidence package / dashboard snapshot.

Execution model (P0-3): callers create a GeneratedReport row in the request
session and commit, then schedule `run_*(report_id, ...)` as
`asyncio.create_task`. Each `run_*` opens its own AsyncSession, loads the
report by id, and updates status on completion. This keeps HTTP responses
fast (~50 ms) regardless of how long the actual rendering takes.
"""

import csv
import hashlib
import io
import logging
import zipfile
from datetime import UTC, date, datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader
from openpyxl import Workbook
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models.aws_config import ConfigEvaluation, ConfigSyncJob
from app.models.compliance import ComplianceSnapshot
from app.models.corrective import CorrectiveAction
from app.models.evidence import Evidence, EvidenceItemLink, EvidenceStatus
from app.models.isms import ISMSDomain, ISMSItem, ISMSSubdomain
from app.models.pipa import DestructionRecord, DSRRequest, Incident, ThirdPartyProcessor
from app.models.prowler import FindingStatus, ProwlerFinding, RemediationStatus, ScanJob, ScanStatus
from app.models.report import GeneratedReport, ReportStatus, ReportType
from app.models.user import User

logger = logging.getLogger("k-compliance.reports")

_TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"
_REPORT_DIR = Path(__file__).resolve().parent.parent.parent / "uploads" / "reports"

_jinja_env = Environment(loader=FileSystemLoader(str(_TEMPLATE_DIR)), autoescape=True)


def _ensure_report_dir() -> Path:
    _REPORT_DIR.mkdir(parents=True, exist_ok=True)
    return _REPORT_DIR


async def _next_report_code(db: AsyncSession) -> str:
    """Generate report code like R-20260405-01, resetting sequence daily (KST)."""
    from zoneinfo import ZoneInfo

    today_str = datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y%m%d")
    prefix = f"R-{today_str}-"
    result = await db.execute(
        select(GeneratedReport.report_code)
        .where(GeneratedReport.report_code.like(f"{prefix}%"))
        .order_by(GeneratedReport.report_code.desc())
        .limit(1)
    )
    last_code = result.scalar_one_or_none()
    if last_code:
        seq = int(last_code.split("-")[-1]) + 1
    else:
        seq = 1
    return f"{prefix}{seq:02d}"


async def prepare_report(
    db: AsyncSession,
    report_type: ReportType,
    title: str,
    period_start: date,
    period_end: date,
    user_id: int,
    assessment_id: int | None = None,
) -> GeneratedReport:
    """Create a GeneratedReport row in status=generating and return it.

    The caller should `await db.commit()` before scheduling the matching
    `run_*` background task.
    """
    report = GeneratedReport(
        report_code=await _next_report_code(db),
        report_type=report_type,
        title=title,
        period_start=period_start,
        period_end=period_end,
        status=ReportStatus.generating,
        generated_by=user_id,
        assessment_id=assessment_id,
    )
    db.add(report)
    await db.flush()
    return report


async def _finalize_failure(report_id: int, exc: Exception) -> None:
    """Best-effort: mark the report failed with the real exception text."""
    msg = f"{type(exc).__name__}: {exc}"[:2000]
    try:
        async with async_session() as db:
            r = (await db.execute(select(GeneratedReport).where(GeneratedReport.id == report_id))).scalar_one_or_none()
            if r and r.status == ReportStatus.generating:
                r.status = ReportStatus.failed
                r.error_message = msg
                await db.commit()
    except Exception:
        logger.exception("report finalize-failure path also failed (report_id=%s)", report_id)


async def run_isms_assessment(report_id: int) -> None:
    """Background worker: renders ISMS-P assessment HTML into the existing report row."""
    try:
        async with async_session() as db:
            report = (
                await db.execute(select(GeneratedReport).where(GeneratedReport.id == report_id))
            ).scalar_one_or_none()
            if not report:
                logger.warning("run_isms_assessment: report %s disappeared", report_id)
                return
            user_name = (
                await db.execute(select(User.name).where(User.id == report.generated_by))
            ).scalar() or "unknown"
            period_start, period_end = report.period_start, report.period_end
            period_label = f"{period_start} ~ {period_end}"

            data = await _collect_assessment_data(db, period_start, period_end)
            data["generated_at"] = datetime.now(UTC).strftime("%Y-%m-%d %H:%M (UTC)")
            data["generated_by"] = user_name
            data["period_label"] = period_label

            template = _jinja_env.get_template("isms_assessment.html")
            html = template.render(**data)

            out_dir = _ensure_report_dir()
            filename = f"isms_assessment_{period_start}_{period_end}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
            filepath = out_dir / filename
            filepath.write_text(html, encoding="utf-8")

            report.status = ReportStatus.completed
            report.file_key = f"reports/{filename}"
            report.file_size = filepath.stat().st_size
            await db.commit()
    except Exception as exc:
        logger.exception("run_isms_assessment failed (report_id=%s)", report_id)
        await _finalize_failure(report_id, exc)


async def _collect_assessment_data(db: AsyncSession, period_start: date, period_end: date) -> dict:
    """Collect all data needed for the ISMS assessment report.

    Uses the latest ComplianceSnapshot per item (current compliance state).
    Snapshots within the date range are used to show assessment activity.
    """
    today = date.today()

    # ── 1. Domains / Items hierarchy ────────────────────────────
    domains_raw = (await db.execute(select(ISMSDomain).order_by(ISMSDomain.sort_order))).scalars().all()

    # Latest snapshot per item (current state — continuous model)
    latest_snap_ids = select(func.max(ComplianceSnapshot.id)).group_by(ComplianceSnapshot.item_id)
    snapshots_result = await db.execute(select(ComplianceSnapshot).where(ComplianceSnapshot.id.in_(latest_snap_ids)))
    snap_map: dict[int, ComplianceSnapshot] = {s.item_id: s for s in snapshots_result.scalars().all()}

    # Evidence count per item (approved)
    ev_counts_result = await db.execute(
        select(
            EvidenceItemLink.item_id,
            func.count().label("total"),
            func.count().filter(Evidence.status == EvidenceStatus.approved).label("approved"),
        )
        .join(Evidence, Evidence.id == EvidenceItemLink.evidence_id)
        .group_by(EvidenceItemLink.item_id)
    )
    ev_map: dict[int, dict] = {r.item_id: {"total": r.total, "approved": r.approved} for r in ev_counts_result.all()}

    total_items = 0
    status_counts = {"compliant": 0, "partial": 0, "non_compliant": 0, "na": 0, "not_assessed": 0}
    all_items = []
    domains = []
    items_without_evidence = []

    for domain in domains_raw:
        subs = (
            (
                await db.execute(
                    select(ISMSSubdomain).where(ISMSSubdomain.domain_id == domain.id).order_by(ISMSSubdomain.sort_order)
                )
            )
            .scalars()
            .all()
        )

        d_counts = {"compliant": 0, "partial": 0, "non_compliant": 0, "na": 0, "not_assessed": 0}
        d_items = []

        for sub in subs:
            items = (
                (
                    await db.execute(
                        select(ISMSItem).where(ISMSItem.subdomain_id == sub.id).order_by(ISMSItem.sort_order)
                    )
                )
                .scalars()
                .all()
            )

            for item in items:
                total_items += 1
                snap = snap_map.get(item.id)
                ev = ev_map.get(item.id, {"total": 0, "approved": 0})

                if snap:
                    status = snap.status.value if hasattr(snap.status, "value") else str(snap.status)
                    if status == "not_applicable":
                        key = "na"
                    else:
                        key = status
                else:
                    status = "not_assessed"
                    key = "not_assessed"

                d_counts[key] = d_counts.get(key, 0) + 1
                status_counts[key] = status_counts.get(key, 0) + 1

                item_data = {
                    "code": item.code,
                    "name": item.name,
                    "domain_code": domain.code,
                    "status": status,
                    "checklist_checked": snap.checklist_checked if snap else 0,
                    "checklist_total": snap.checklist_total if snap else 0,
                    "evidence_approved": ev["approved"],
                    "evidence_total": ev["total"],
                    "prowler_passed": snap.prowler_passed if snap else 0,
                    "prowler_total": snap.prowler_total if snap else 0,
                    "config_compliant": snap.config_compliant if snap else 0,
                    "config_total": snap.config_total if snap else 0,
                    "assessed_at": snap.assessed_at.strftime("%Y-%m-%d %H:%M") if snap and snap.assessed_at else None,
                    "notes": snap.notes if snap else None,
                }
                d_items.append(item_data)
                all_items.append(item_data)

                if ev["approved"] == 0:
                    items_without_evidence.append(item_data)

        d_total = sum(d_counts.values())
        d_compliant = d_counts["compliant"]
        domains.append(
            {
                "code": domain.code,
                "name": domain.name,
                "total": d_total,
                "compliant": d_compliant,
                "partial": d_counts["partial"],
                "non_compliant": d_counts["non_compliant"],
                "na": d_counts["na"],
                "not_assessed": d_counts["not_assessed"],
                "compliance_rate": round(d_compliant / d_total * 100, 1) if d_total > 0 else 0,
                "item_list": d_items,
            }
        )

    compliance_rate = round(status_counts["compliant"] / total_items * 100, 1) if total_items > 0 else 0

    # ── 2. Evidence stats ───────────────────────────────────────
    ev_result = await db.execute(select(Evidence.status, func.count()).group_by(Evidence.status))
    ev_raw = dict(ev_result.all())
    evidence_stats = {
        "total": sum(ev_raw.values()),
        "approved": ev_raw.get(EvidenceStatus.approved, 0),
        "submitted": ev_raw.get(EvidenceStatus.submitted, 0),
        "draft": ev_raw.get(EvidenceStatus.draft, 0),
        "rejected": ev_raw.get(EvidenceStatus.rejected, 0),
        "expired": ev_raw.get(EvidenceStatus.expired, 0),
    }

    # Evidence records with linked ISMS item codes
    all_evidence = (await db.execute(select(Evidence).order_by(Evidence.id))).scalars().all()

    ev_link_result = await db.execute(
        select(EvidenceItemLink.evidence_id, ISMSItem.code).join(ISMSItem, ISMSItem.id == EvidenceItemLink.item_id)
    )
    ev_links_map: dict[int, list[str]] = {}
    for eid, code in ev_link_result.all():
        ev_links_map.setdefault(eid, []).append(code)

    evidence_type_labels = {
        "document": "문서",
        "prowler": "Prowler",
        "pipa_record": "PIPA 기록",
        "external_link": "외부 링크",
    }
    evidence_status_labels = {
        "draft": "초안",
        "submitted": "제출",
        "approved": "승인",
        "rejected": "반려",
        "expired": "만료",
        "replaced": "대체됨",
    }
    evidence_records = []
    for ev in all_evidence:
        ev_type_val = ev.evidence_type.value if hasattr(ev.evidence_type, "value") else str(ev.evidence_type)
        ev_status_val = ev.status.value if hasattr(ev.status, "value") else str(ev.status)
        evidence_records.append(
            {
                "id": ev.id,
                "title": ev.title,
                "linked_items": ", ".join(sorted(ev_links_map.get(ev.id, []))) or "-",
                "evidence_type": evidence_type_labels.get(ev_type_val, ev_type_val),
                "status": ev_status_val,
                "status_label": evidence_status_labels.get(ev_status_val, ev_status_val),
                "valid_to": str(ev.valid_to) if ev.valid_to else "무기한",
                "version": ev.version,
            }
        )

    # ── 3. Corrective actions ──────────────────────────────────
    ca_result = await db.execute(select(CorrectiveAction.status, func.count()).group_by(CorrectiveAction.status))
    ca_raw = dict(ca_result.all())
    corrective_stats = {
        "open": ca_raw.get("open", 0),
        "in_progress": ca_raw.get("in_progress", 0),
        "completed": ca_raw.get("completed", 0),
        "verified": ca_raw.get("verified", 0),
        "overdue": ca_raw.get("overdue", 0),
        "open_total": ca_raw.get("open", 0) + ca_raw.get("in_progress", 0),
    }

    open_cas = (
        await db.execute(
            select(CorrectiveAction, ISMSItem.code.label("item_code"))
            .outerjoin(ISMSItem, ISMSItem.id == CorrectiveAction.isms_item_id)
            .where(CorrectiveAction.status.in_(["open", "in_progress", "overdue"]))
            .order_by(CorrectiveAction.due_date)
        )
    ).all()

    corrective_actions = []
    for row in open_cas:
        ca = row[0]
        item_code = row[1]
        d_day = (ca.due_date - today).days
        source_label = {
            "external_audit": "외부감사",
            "internal_review": "내부점검",
            "prowler": "Prowler",
            "config": "Config",
            "other": "기타",
        }.get(ca.source.value if hasattr(ca.source, "value") else str(ca.source), str(ca.source))
        corrective_actions.append(
            {
                "id": ca.id,
                "title": ca.title,
                "status": ca.status.value if hasattr(ca.status, "value") else str(ca.status),
                "source": source_label,
                "item_code": item_code,
                "due_date": str(ca.due_date),
                "d_day": d_day,
            }
        )

    # ── 4. Prowler summary ─────────────────────────────────────
    latest_scan = (
        await db.execute(select(ScanJob).where(ScanJob.status == ScanStatus.completed).order_by(ScanJob.id.desc()))
    ).scalar_one_or_none()

    prowler_stats = {"total": 0, "passed": 0, "failed": 0, "remediation_pending": 0, "scanned_at": None}
    if latest_scan:
        remediation = (
            await db.execute(
                select(func.count())
                .select_from(ProwlerFinding)
                .where(
                    ProwlerFinding.scan_job_id == latest_scan.id,
                    ProwlerFinding.status == FindingStatus.FAIL,
                    ProwlerFinding.remediation_status == RemediationStatus.open,
                )
            )
        ).scalar()
        prowler_stats = {
            "total": latest_scan.total_checks or 0,
            "passed": latest_scan.passed or 0,
            "failed": latest_scan.failed or 0,
            "remediation_pending": remediation or 0,
            "scanned_at": latest_scan.completed_at.strftime("%Y-%m-%d %H:%M") if latest_scan.completed_at else None,
        }

    # ── 5. Config summary ──────────────────────────────────────
    latest_sync = (
        await db.execute(
            select(ConfigSyncJob).where(ConfigSyncJob.status == ScanStatus.completed).order_by(ConfigSyncJob.id.desc())
        )
    ).scalar_one_or_none()

    config_stats = {"total_rules": 0, "compliant": 0, "non_compliant": 0, "remediation_pending": 0, "synced_at": None}
    if latest_sync:
        config_remediation = (
            await db.execute(
                select(func.count())
                .select_from(ConfigEvaluation)
                .where(
                    ConfigEvaluation.sync_job_id == latest_sync.id,
                    ConfigEvaluation.compliance_type == "NON_COMPLIANT",
                    ConfigEvaluation.remediation_status == RemediationStatus.open,
                )
            )
        ).scalar()
        config_stats = {
            "total_rules": latest_sync.total_rules or 0,
            "compliant": latest_sync.compliant or 0,
            "non_compliant": latest_sync.non_compliant or 0,
            "remediation_pending": config_remediation or 0,
            "synced_at": latest_sync.completed_at.strftime("%Y-%m-%d %H:%M") if latest_sync.completed_at else None,
        }

    # ── 6. Automation coverage ─────────────────────────────────
    prowler_items = (
        await db.execute(select(func.count()).select_from(ISMSItem).where(ISMSItem.has_prowler_checks == True))
    ).scalar()
    config_items = (
        await db.execute(select(func.count()).select_from(ISMSItem).where(ISMSItem.has_config_rules == True))
    ).scalar()
    both = (
        await db.execute(
            select(func.count())
            .select_from(ISMSItem)
            .where(ISMSItem.has_prowler_checks == True, ISMSItem.has_config_rules == True)
        )
    ).scalar()
    covered = prowler_items + config_items - both

    automation_stats = {
        "covered": covered,
        "coverage_rate": round(covered / total_items * 100, 1) if total_items > 0 else 0,
    }

    # ── 7. Trend data (by month) ──────────────────────────────
    month_expr = func.to_char(ComplianceSnapshot.assessed_at, "YYYY-MM")
    trend_result = await db.execute(
        select(
            month_expr.label("month"),
            ISMSDomain.code.label("domain_code"),
            func.count().label("total"),
            func.count().filter(ComplianceSnapshot.status == "compliant").label("compliant"),
        )
        .join(ISMSItem, ISMSItem.id == ComplianceSnapshot.item_id)
        .join(ISMSSubdomain, ISMSSubdomain.id == ISMSItem.subdomain_id)
        .join(ISMSDomain, ISMSDomain.id == ISMSSubdomain.domain_id)
        .group_by(month_expr, ISMSDomain.code)
        .order_by(month_expr, ISMSDomain.code)
    )
    trend_data = [
        {"period": r.month, "domain_code": r.domain_code, "total": r.total, "compliant": r.compliant}
        for r in trend_result.all()
    ]

    return {
        "total_items": total_items,
        "compliance_rate": compliance_rate,
        "status_counts": status_counts,
        "domains": domains,
        "all_items": all_items,
        "items_without_evidence": items_without_evidence,
        "evidence_stats": evidence_stats,
        "evidence_records": evidence_records,
        "corrective_stats": corrective_stats,
        "corrective_actions": corrective_actions,
        "prowler_stats": prowler_stats,
        "config_stats": config_stats,
        "automation_stats": automation_stats,
        "trend_data": trend_data if len(set(d["period"] for d in trend_data)) > 1 else [],
    }


def get_report_path(file_key: str) -> Path | None:
    """Resolve file_key to a local file path."""
    base = Path(__file__).resolve().parent.parent.parent / "uploads"
    path = base / file_key
    return path if path.is_file() else None


# ═══════════════════════════════════════════════════════════════════
# T7.3 Corrective Action Report
# ═══════════════════════════════════════════════════════════════════


async def run_corrective_action_report(report_id: int) -> None:
    """Background worker: renders corrective-action HTML + CSV into the existing report row."""
    try:
        async with async_session() as db:
            report = (
                await db.execute(select(GeneratedReport).where(GeneratedReport.id == report_id))
            ).scalar_one_or_none()
            if not report:
                logger.warning("run_corrective_action_report: report %s disappeared", report_id)
                return
            user_name = (
                await db.execute(select(User.name).where(User.id == report.generated_by))
            ).scalar() or "unknown"
            period_start, period_end = report.period_start, report.period_end
            period_label = f"{period_start} ~ {period_end}"

            data = await _collect_corrective_data(db, period_start, period_end)
            data["generated_at"] = datetime.now(UTC).strftime("%Y-%m-%d %H:%M (UTC)")
            data["generated_by"] = user_name
            data["period_label"] = period_label

            template = _jinja_env.get_template("corrective_action.html")
            html = template.render(**data)

            out_dir = _ensure_report_dir()
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            html_name = f"corrective_{period_start}_{period_end}_{ts}.html"
            (out_dir / html_name).write_text(html, encoding="utf-8")

            # CSV export (sibling file)
            csv_name = html_name.replace(".html", ".csv")
            csv_path = out_dir / csv_name
            with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(
                    ["ID", "제목", "출처", "ISMS-P 항목", "담당자", "기한", "상태", "D-Day", "완료일", "검증일", "결과"]
                )
                for r in data["rows"]:
                    writer.writerow(
                        [
                            r["id"],
                            r["title"],
                            r["source_label"],
                            r["item_code"] or "",
                            r["assignee"] or "",
                            r["due_date"],
                            r["status_label"],
                            r["d_day"],
                            r["completed_at"] or "",
                            r["verified_at"] or "",
                            (r["result"] or "").replace("\n", " ")[:500],
                        ]
                    )

            report.status = ReportStatus.completed
            report.file_key = f"reports/{html_name}"
            report.file_size = (out_dir / html_name).stat().st_size
            await db.commit()
    except Exception as exc:
        logger.exception("run_corrective_action_report failed (report_id=%s)", report_id)
        await _finalize_failure(report_id, exc)


async def _collect_corrective_data(db: AsyncSession, period_start: date, period_end: date) -> dict:
    """Collect corrective action statistics + full list."""
    today = date.today()

    # All corrective actions created OR closed within period (inclusive)
    q = (await db.execute(select(CorrectiveAction).order_by(CorrectiveAction.due_date))).scalars().all()

    # Join item codes
    item_id_set = {ca.isms_item_id for ca in q if ca.isms_item_id}
    item_map: dict[int, str] = {}
    if item_id_set:
        rows = (await db.execute(select(ISMSItem.id, ISMSItem.code).where(ISMSItem.id.in_(item_id_set)))).all()
        item_map = {r.id: r.code for r in rows}

    # User names
    user_ids = {ca.assigned_to for ca in q if ca.assigned_to}
    user_map: dict[int, str] = {}
    if user_ids:
        rows = (await db.execute(select(User.id, User.name).where(User.id.in_(user_ids)))).all()
        user_map = {r.id: r.name for r in rows}

    source_labels = {
        "external_audit": "외부감사",
        "internal_review": "내부점검",
        "prowler": "Prowler",
        "config": "AWS Config",
        "other": "기타",
    }
    status_labels = {
        "open": "미착수",
        "in_progress": "진행중",
        "completed": "조치완료",
        "verified": "검증완료",
        "overdue": "기한초과",
    }

    counts = {k: 0 for k in status_labels}
    source_counts = {k: 0 for k in source_labels}
    overdue_items = []
    rows_out = []

    for ca in q:
        st = ca.status.value if hasattr(ca.status, "value") else str(ca.status)
        src = ca.source.value if hasattr(ca.source, "value") else str(ca.source)
        counts[st] = counts.get(st, 0) + 1
        source_counts[src] = source_counts.get(src, 0) + 1

        d_day = (ca.due_date - today).days
        is_overdue = (st == "overdue") or (st in ("open", "in_progress") and d_day < 0)

        row = {
            "id": ca.id,
            "title": ca.title,
            "source": src,
            "source_label": source_labels.get(src, src),
            "item_code": item_map.get(ca.isms_item_id) if ca.isms_item_id else None,
            "assignee": user_map.get(ca.assigned_to) if ca.assigned_to else None,
            "due_date": str(ca.due_date),
            "status": st,
            "status_label": status_labels.get(st, st),
            "d_day": d_day,
            "is_overdue": is_overdue,
            "completed_at": ca.completed_at.strftime("%Y-%m-%d") if ca.completed_at else None,
            "verified_at": ca.verified_at.strftime("%Y-%m-%d") if ca.verified_at else None,
            "result": ca.result,
            "description": ca.description,
        }
        rows_out.append(row)
        if is_overdue:
            overdue_items.append(row)

    total = len(rows_out)
    closed = counts.get("completed", 0) + counts.get("verified", 0)
    progress_rate = round(closed / total * 100, 1) if total > 0 else 0

    return {
        "total": total,
        "counts": counts,
        "source_counts": source_counts,
        "overdue_count": len(overdue_items),
        "overdue_items": overdue_items,
        "rows": rows_out,
        "progress_rate": progress_rate,
        "closed": closed,
        "open": counts.get("open", 0) + counts.get("in_progress", 0) + counts.get("overdue", 0),
    }


# ═══════════════════════════════════════════════════════════════════
# T7.2 Evidence Package (ZIP)
# ═══════════════════════════════════════════════════════════════════


async def run_evidence_package(
    report_id: int,
    domain_filter: str | None = None,
    status_filter: str = "approved",
    include_evidence_ids: list[int] | None = None,
    exclude_evidence_ids: list[int] | None = None,
) -> None:
    """Background worker: renders evidence package ZIP into the existing report row.

    Selection precedence:
    - `include_evidence_ids` (non-empty) → use only those IDs, ignore
      domain/status filters. Evidence is still grouped by its linked ISMS
      items; an evidence with no item link is dropped from the ZIP.
    - Otherwise → broad filter by domain_filter + status_filter.
    - `exclude_evidence_ids` is always subtracted from the final set.
    """
    include_set = set(include_evidence_ids or [])
    exclude_set = set(exclude_evidence_ids or [])
    try:
        async with async_session() as db:
            report = (
                await db.execute(select(GeneratedReport).where(GeneratedReport.id == report_id))
            ).scalar_one_or_none()
            if not report:
                logger.warning("run_evidence_package: report %s disappeared", report_id)
                return
            user_name = (
                await db.execute(select(User.name).where(User.id == report.generated_by))
            ).scalar() or "unknown"
            period_start, period_end = report.period_start, report.period_end
            period_label = f"{period_start} ~ {period_end}"

            buf = io.BytesIO()
            manifest_lines: list[str] = []
            summary_rows: list[dict] = []
            total_files = 0
            included_items = 0

            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                domains = (await db.execute(select(ISMSDomain).order_by(ISMSDomain.sort_order))).scalars().all()

                for domain in domains:
                    if domain_filter and domain.code != domain_filter:
                        continue
                    subs = (
                        (
                            await db.execute(
                                select(ISMSSubdomain)
                                .where(ISMSSubdomain.domain_id == domain.id)
                                .order_by(ISMSSubdomain.sort_order)
                            )
                        )
                        .scalars()
                        .all()
                    )

                    for sub in subs:
                        items = (
                            (
                                await db.execute(
                                    select(ISMSItem)
                                    .where(ISMSItem.subdomain_id == sub.id)
                                    .order_by(ISMSItem.sort_order)
                                )
                            )
                            .scalars()
                            .all()
                        )

                        for item in items:
                            ev_q = (
                                select(Evidence)
                                .join(EvidenceItemLink, EvidenceItemLink.evidence_id == Evidence.id)
                                .where(EvidenceItemLink.item_id == item.id)
                            )
                            if include_set:
                                # Curated mode — status/domain not applied here;
                                # the caller has already picked the rows they want.
                                ev_q = ev_q.where(Evidence.id.in_(include_set))
                            elif status_filter:
                                ev_q = ev_q.where(Evidence.status == EvidenceStatus(status_filter))
                            if exclude_set:
                                ev_q = ev_q.where(Evidence.id.notin_(exclude_set))
                            evidence_list = (await db.execute(ev_q)).scalars().all()

                            if not evidence_list:
                                continue

                            included_items += 1
                            item_dir = f"{item.code}_{_safe_name(item.name)[:40]}"
                            item_rows = []

                            for ev in evidence_list:
                                data = await _read_evidence_bytes(ev)
                                fname = ev.file_name or f"evidence_{ev.id}"
                                if data is not None:
                                    zf.writestr(f"{item_dir}/{fname}", data)
                                    file_hash = hashlib.sha256(data).hexdigest()
                                    manifest_lines.append(f"{file_hash}  {item_dir}/{fname}")
                                    total_files += 1
                                elif ev.external_url:
                                    zf.writestr(
                                        f"{item_dir}/link_{ev.id}.url", f"[InternetShortcut]\nURL={ev.external_url}"
                                    )
                                    total_files += 1

                                ev_type = (
                                    ev.evidence_type.value
                                    if hasattr(ev.evidence_type, "value")
                                    else str(ev.evidence_type)
                                )
                                ev_status = ev.status.value if hasattr(ev.status, "value") else str(ev.status)
                                item_rows.append(
                                    {
                                        "id": ev.id,
                                        "title": ev.title,
                                        "file_name": fname if data else (ev.external_url or "-"),
                                        "type": ev_type,
                                        "status": ev_status,
                                        "version": ev.version,
                                        "valid_from": str(ev.valid_from) if ev.valid_from else "",
                                        "valid_to": str(ev.valid_to) if ev.valid_to else "",
                                        "hash": hashlib.sha256(data).hexdigest() if data else "",
                                    }
                                )

                            # Per-item metadata CSV
                            csv_buf = io.StringIO()
                            writer = csv.writer(csv_buf)
                            writer.writerow(
                                ["증적ID", "제목", "파일명", "유형", "상태", "버전", "유효시작", "유효종료", "SHA256"]
                            )
                            for r in item_rows:
                                writer.writerow(
                                    [
                                        r["id"],
                                        r["title"],
                                        r["file_name"],
                                        r["type"],
                                        r["status"],
                                        r["version"],
                                        r["valid_from"],
                                        r["valid_to"],
                                        r["hash"],
                                    ]
                                )
                            zf.writestr(f"{item_dir}/metadata.csv", csv_buf.getvalue().encode("utf-8-sig"))

                            summary_rows.append(
                                {
                                    "domain_code": domain.code,
                                    "domain_name": domain.name,
                                    "item_code": item.code,
                                    "item_name": item.name,
                                    "evidence_count": len(item_rows),
                                    "dir": item_dir,
                                }
                            )

                # XLSX summary
                wb = Workbook()
                ws = wb.active
                ws.title = "증적 요약"
                ws.append(["도메인", "도메인명", "항목코드", "항목명", "증적수", "폴더"])
                for r in summary_rows:
                    ws.append(
                        [
                            r["domain_code"],
                            r["domain_name"],
                            r["item_code"],
                            r["item_name"],
                            r["evidence_count"],
                            r["dir"],
                        ]
                    )
                xlsx_buf = io.BytesIO()
                wb.save(xlsx_buf)
                zf.writestr("evidence_summary.xlsx", xlsx_buf.getvalue())

                # MANIFEST
                zf.writestr("MANIFEST.sha256", "\n".join(manifest_lines) + "\n")

                # index.html
                index_html = _build_evidence_index(period_label, summary_rows, total_files, user_name)
                zf.writestr("index.html", index_html)

            zip_data = buf.getvalue()
            out_dir = _ensure_report_dir()
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            zip_name = f"evidence_package_{period_start}_{period_end}_{ts}.zip"
            (out_dir / zip_name).write_bytes(zip_data)

            report.status = ReportStatus.completed
            report.file_key = f"reports/{zip_name}"
            report.file_size = len(zip_data)
            await db.commit()
    except Exception as exc:
        logger.exception("run_evidence_package failed (report_id=%s)", report_id)
        await _finalize_failure(report_id, exc)


def _safe_name(name: str) -> str:
    """Replace filesystem-unsafe characters for zip entry names."""
    out = []
    for c in name:
        if c.isalnum() or c in " _-.()가-힣":
            out.append(c)
        else:
            out.append("_")
    return "".join(out).strip().replace(" ", "_")


async def _read_evidence_bytes(ev: Evidence) -> bytes | None:
    """Read evidence bytes from S3 or local fallback.

    The local fallback stores objects with slashes collapsed to underscores
    (see evidence_service.upload_to_s3), so file_key "evidence/27/ev1.pdf"
    lands at "<uploads/evidence>/evidence_27_ev1.pdf" — mirror that here.
    """
    if not ev.file_key:
        return None
    from app.services.evidence_service import LOCAL_STORAGE_DIR, _use_local

    if _use_local:
        local_path = LOCAL_STORAGE_DIR / ev.file_key.replace("/", "_")
        if local_path.is_file():
            return local_path.read_bytes()
        return None
    try:
        from app.config import settings
        from app.services.evidence_service import _s3

        obj = _s3.get_object(Bucket=settings.S3_BUCKET_NAME, Key=ev.file_key)
        return obj["Body"].read()
    except Exception:
        return None


def _build_evidence_index(period_label: str, rows: list[dict], total_files: int, generator: str) -> str:
    """Render a simple HTML index for the evidence package."""
    rows_html = "\n".join(
        f"<tr><td>{r['domain_code']}</td><td>{r['item_code']}</td>"
        f"<td>{r['item_name']}</td><td>{r['evidence_count']}</td>"
        f'<td><a href="{r["dir"]}/metadata.csv">metadata.csv</a></td></tr>'
        for r in rows
    )
    now_str = datetime.now(UTC).strftime("%Y-%m-%d %H:%M (UTC)")
    return f"""<!DOCTYPE html><html lang="ko"><head><meta charset="UTF-8">
<title>증적 패키지 — {period_label}</title>
<style>
body{{font-family:-apple-system,'Malgun Gothic',sans-serif;padding:24px;max-width:1100px;margin:0 auto}}
table{{width:100%;border-collapse:collapse;margin-top:16px}}
th,td{{padding:8px 10px;border:1px solid #e2e8f0;font-size:13px}}
th{{background:#f1f5f9}} .meta{{background:#f8fafc;padding:12px;border-radius:6px;margin-bottom:16px}}
</style></head><body>
<h1>ISMS-P 증적 패키지</h1>
<div class="meta">
<strong>기간:</strong> {period_label}<br>
<strong>생성:</strong> {now_str} ({generator})<br>
<strong>포함 항목:</strong> {len(rows)}개 / <strong>파일:</strong> {total_files}개<br>
<strong>무결성:</strong> <a href="MANIFEST.sha256">MANIFEST.sha256</a> /
<strong>요약:</strong> <a href="evidence_summary.xlsx">evidence_summary.xlsx</a>
</div>
<table>
<thead><tr><th>도메인</th><th>항목코드</th><th>항목명</th><th>증적수</th><th>메타데이터</th></tr></thead>
<tbody>{rows_html}</tbody></table>
</body></html>"""


# ═══════════════════════════════════════════════════════════════════
# T7.4 Dashboard Snapshot (print-friendly HTML; browser PDF export)
# ═══════════════════════════════════════════════════════════════════


async def run_dashboard_snapshot(report_id: int) -> None:
    """Background worker: renders print-friendly dashboard HTML into the existing report row.

    Note: Server-side PDF conversion (weasyprint/playwright) is not installed.
    The HTML is designed with @page CSS so browsers can 'Print → Save as PDF'.
    """
    try:
        async with async_session() as db:
            report = (
                await db.execute(select(GeneratedReport).where(GeneratedReport.id == report_id))
            ).scalar_one_or_none()
            if not report:
                logger.warning("run_dashboard_snapshot: report %s disappeared", report_id)
                return
            user_name = (
                await db.execute(select(User.name).where(User.id == report.generated_by))
            ).scalar() or "unknown"
            today = date.today()

            # Reuse ISMS assessment data (full year as period)
            year_start = date(today.year, 1, 1)
            data = await _collect_assessment_data(db, year_start, today)

            # Add PIPA + incident snapshots
            dsr_overdue = (
                await db.execute(select(func.count()).select_from(DSRRequest).where(DSRRequest.status == "overdue"))
            ).scalar() or 0
            dest_overdue = (
                await db.execute(
                    select(func.count()).select_from(DestructionRecord).where(DestructionRecord.status == "overdue")
                )
            ).scalar() or 0
            incident_open = (
                await db.execute(
                    select(func.count()).select_from(Incident).where(Incident.status.notin_(["resolved", "closed"]))
                )
            ).scalar() or 0
            contract_expiring = (
                await db.execute(
                    select(func.count())
                    .select_from(ThirdPartyProcessor)
                    .where(
                        ThirdPartyProcessor.is_active == True,
                        ThirdPartyProcessor.contract_end >= today,
                        ThirdPartyProcessor.contract_end <= date(today.year, today.month, min(today.day + 30, 28)),
                    )
                )
            ).scalar() or 0

            data["generated_at"] = datetime.now(UTC).strftime("%Y-%m-%d %H:%M (UTC)")
            data["generated_by"] = user_name
            data["period_label"] = f"{today} 기준"
            data["pipa_snapshot"] = {
                "dsr_overdue": dsr_overdue,
                "destruction_overdue": dest_overdue,
                "incident_open": incident_open,
                "contract_expiring_30d": contract_expiring,
            }

            template = _jinja_env.get_template("dashboard_snapshot.html")
            html = template.render(**data)

            out_dir = _ensure_report_dir()
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            fname = f"dashboard_snapshot_{today}_{ts}.html"
            (out_dir / fname).write_text(html, encoding="utf-8")

            report.status = ReportStatus.completed
            report.file_key = f"reports/{fname}"
            report.file_size = (out_dir / fname).stat().st_size
            await db.commit()
    except Exception as exc:
        logger.exception("run_dashboard_snapshot failed (report_id=%s)", report_id)
        await _finalize_failure(report_id, exc)
