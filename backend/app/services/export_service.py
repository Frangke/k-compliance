"""Evidence package export — ZIP with directory structure, manifest, and summary."""

import hashlib
import io
import zipfile
from datetime import UTC, datetime

from openpyxl import Workbook
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.compliance import ComplianceSnapshot
from app.models.evidence import Evidence, EvidenceItemLink
from app.models.export import ExportJob, ExportStatus
from app.models.isms import ISMSDomain, ISMSItem, ISMSSubdomain
from app.services.evidence_service import _s3


async def export_evidence_package(db: AsyncSession, job: ExportJob) -> None:
    """Build ZIP with evidence files organized by domain/item."""
    job.status = ExportStatus.processing
    job.started_at = datetime.now(UTC)
    await db.commit()

    try:
        options = job.options or {}
        status_filter = options.get("status_filter", "approved")
        buf = io.BytesIO()
        manifest_lines = []

        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            # Compliance summary XLSX
            wb = Workbook()
            ws = wb.active
            ws.title = "준수 현황"
            ws.append(["코드", "항목명", "도메인", "준수상태", "증적수", "체크리스트"])

            domains = (await db.execute(select(ISMSDomain).order_by(ISMSDomain.sort_order))).scalars()
            processed = 0

            for domain in domains:
                subs = (
                    await db.execute(
                        select(ISMSSubdomain)
                        .where(ISMSSubdomain.domain_id == domain.id)
                        .order_by(ISMSSubdomain.sort_order)
                    )
                ).scalars()

                domain_dir = f"{domain.code}_{domain.name.replace(' ', '_')}"

                for sub in subs:
                    items = (
                        await db.execute(
                            select(ISMSItem).where(ISMSItem.subdomain_id == sub.id).order_by(ISMSItem.sort_order)
                        )
                    ).scalars()

                    for item in items:
                        item_dir = f"{domain_dir}/{item.code}_{item.name.replace(' ', '_')[:30]}"

                        # Get linked evidence
                        links = (
                            await db.execute(
                                select(Evidence)
                                .join(EvidenceItemLink)
                                .where(EvidenceItemLink.item_id == item.id)
                                .where(Evidence.status == status_filter if status_filter else True)
                            )
                        ).scalars()

                        ev_count = 0
                        for ev in links:
                            if ev.file_key:
                                try:
                                    obj = _s3.get_object(Bucket=settings.S3_BUCKET_NAME, Key=ev.file_key)
                                    data = obj["Body"].read()
                                    fname = ev.file_name or f"evidence_{ev.id}"
                                    zf.writestr(f"{item_dir}/{fname}", data)
                                    file_hash = hashlib.sha256(data).hexdigest()
                                    manifest_lines.append(f"{file_hash}  {item_dir}/{fname}")
                                except Exception:
                                    pass  # S3 file missing — skip
                            elif ev.external_url:
                                zf.writestr(
                                    f"{item_dir}/link_{ev.id}.url", f"[InternetShortcut]\nURL={ev.external_url}"
                                )

                            ev_count += 1

                        # Compliance snapshot
                        snap = (
                            await db.execute(
                                select(ComplianceSnapshot)
                                .where(ComplianceSnapshot.item_id == item.id)
                                .order_by(ComplianceSnapshot.assessed_at.desc())
                            )
                        ).scalar_one_or_none()
                        status_str = snap.status.value if snap else "미평가"

                        ws.append([item.code, item.name, domain.name, status_str, ev_count, ""])
                        processed += 1
                        job.processed_items = processed
                        # Don't commit in tight loop — batch at end

            # Write XLSX to ZIP
            xlsx_buf = io.BytesIO()
            wb.save(xlsx_buf)
            zf.writestr("compliance_summary.xlsx", xlsx_buf.getvalue())

            # Write manifest
            zf.writestr("MANIFEST.sha256", "\n".join(manifest_lines))

            # Write index.html
            index_html = "<html><head><title>K-Compliance Evidence Export</title></head><body>"
            index_html += f"<h1>증적 패키지</h1><p>생성: {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>"
            index_html += f"<p>항목: {processed}개</p>"
            index_html += "<p><a href='compliance_summary.xlsx'>준수 현황 요약 (XLSX)</a></p>"
            index_html += "</body></html>"
            zf.writestr("index.html", index_html)

        # Upload to S3
        zip_data = buf.getvalue()
        s3_key = f"exports/export_{job.id}.zip"
        _s3.put_object(Bucket=settings.S3_BUCKET_NAME, Key=s3_key, Body=zip_data, ContentType="application/zip")

        job.status = ExportStatus.completed
        job.file_key = s3_key
        job.file_size = len(zip_data)
        job.total_items = processed
        job.processed_items = processed
        job.completed_at = datetime.now(UTC)
        await db.commit()

    except Exception as e:
        job.status = ExportStatus.failed
        job.error_message = str(e)[:2000]
        job.completed_at = datetime.now(UTC)
        await db.commit()
