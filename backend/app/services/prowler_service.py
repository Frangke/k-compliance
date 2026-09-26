"""Prowler scan execution — async subprocess + OCSF JSON parsing.

Background execution: `start_scan(scan_job_id)` opens its own AsyncSession.
Never pass a request-scoped session in, because FastAPI closes it as soon as
the HTTP response returns.
"""

import asyncio
import json
import logging
import os
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import async_session
from app.models.prowler import (
    CloudAccount,
    FindingSeverity,
    FindingStatus,
    ProwlerFinding,
    ScanJob,
    ScanStatus,
)
from app.services.aws_session import get_credentials_env
from app.services.crypto import decrypt_json

logger = logging.getLogger("k-compliance.prowler")

# Prowler mapping: check_id → isms_item_id (loaded from seed)
_prowler_mapping: dict[str, int] = {}


async def load_prowler_mapping(db: AsyncSession):
    """Load prowler_mapping.json → dict of check_id → isms_item_id."""
    global _prowler_mapping
    mapping_file = Path(__file__).parent.parent / "seeds" / "prowler_mapping.json"
    if not mapping_file.exists():
        return

    with open(mapping_file) as f:
        raw = json.load(f)

    from app.models.isms import ISMSItem

    if isinstance(raw, dict):
        for check_id, item_code in raw.items():
            result = await db.execute(select(ISMSItem.id).where(ISMSItem.code == item_code))
            item_id = result.scalar_one_or_none()
            if item_id:
                _prowler_mapping[check_id] = item_id
    elif isinstance(raw, list):
        for entry in raw:
            check_id = entry.get("check_id") or entry.get("prowler_check")
            item_code = entry.get("isms_item_code") or entry.get("isms_code")
            if check_id and item_code:
                result = await db.execute(select(ISMSItem.id).where(ISMSItem.code == item_code))
                item_id = result.scalar_one_or_none()
                if item_id:
                    _prowler_mapping[check_id] = item_id


async def start_scan(scan_job_id: int) -> None:
    """Run Prowler in the background with its own AsyncSession.

    The caller (api/prowler.py) schedules this via asyncio.create_task(...)
    AFTER the request transaction has committed. This function opens a fresh
    session so the closed request session cannot affect it.
    """
    async with async_session() as db:
        try:
            await _run_scan(db, scan_job_id)
        except Exception as exc:
            logger.exception("start_scan failed (scan_job_id=%s)", scan_job_id)
            msg = f"{type(exc).__name__}: {exc}"[:2000]
            try:
                async with async_session() as db2:
                    job = (await db2.execute(select(ScanJob).where(ScanJob.id == scan_job_id))).scalar_one_or_none()
                    if job and job.status not in (ScanStatus.completed, ScanStatus.cancelled):
                        job.status = ScanStatus.failed
                        job.error_message = msg
                        job.completed_at = datetime.now(UTC)
                        await db2.commit()
            except Exception:
                logger.exception("start_scan recovery path also failed")


async def _run_scan(db: AsyncSession, scan_job_id: int) -> None:
    scan_job = (await db.execute(select(ScanJob).where(ScanJob.id == scan_job_id))).scalar_one_or_none()
    if not scan_job:
        logger.warning("start_scan: scan_job %s disappeared", scan_job_id)
        return

    output_dir = f"{settings.PROWLER_OUTPUT_DIR}/{scan_job.id}"
    os.makedirs(output_dir, exist_ok=True)

    scan_job.status = ScanStatus.running
    scan_job.started_at = datetime.now(UTC)
    await db.commit()

    # Resolve AWS credentials from the associated cloud account
    env = os.environ.copy()
    if scan_job.cloud_account_id:
        acc = (
            await db.execute(select(CloudAccount).where(CloudAccount.id == scan_job.cloud_account_id))
        ).scalar_one_or_none()
        if acc:
            cred: dict = {}
            if acc.credentials:
                try:
                    cred = decrypt_json(acc.credentials)
                except Exception:
                    cred = {}
            try:
                env.update(
                    get_credentials_env(
                        auth_type=acc.auth_type or "instance_role",
                        region=acc.default_region or "ap-northeast-2",
                        role_arn=cred.get("role_arn"),
                        external_id=cred.get("external_id"),
                    )
                )
            except Exception as e:
                scan_job.status = ScanStatus.failed
                scan_job.error_message = f"자격증명 준비 실패: {str(e)[:500]}"
                scan_job.completed_at = datetime.now(UTC)
                await db.commit()
                return

    try:
        process = await asyncio.create_subprocess_exec(
            settings.PROWLER_BIN_PATH,
            "aws",
            "--compliance",
            scan_job.compliance or "kisa_isms_p_2023_aws",
            "--output-formats",
            "json-ocsf",
            "--output-directory",
            output_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        try:
            _, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=settings.PROWLER_TIMEOUT_SECONDS,
            )
        except TimeoutError:
            # Prowler hung — kill the process and mark the job failed so the
            # scan doesn't sit in 'running' forever. Close the stdio pipes
            # explicitly before wait(), otherwise an orphaned grandchild that
            # still holds the pipe will keep us blocked on pipe EOF.
            process.kill()
            for pipe in (process.stdout, process.stderr):
                if pipe is not None:
                    try:
                        pipe.feed_eof()
                    except Exception:
                        pass
            try:
                await asyncio.wait_for(process.wait(), timeout=5)
            except Exception:
                pass
            scan_job.status = ScanStatus.failed
            scan_job.error_message = f"스캔 타임아웃 ({settings.PROWLER_TIMEOUT_SECONDS}초 초과)"
            scan_job.completed_at = datetime.now(UTC)
            await db.commit()
            return

        if process.returncode != 0 and process.returncode != 3:
            # returncode 3 = prowler found failures (normal)
            scan_job.status = ScanStatus.failed
            scan_job.error_message = stderr.decode()[:2000] if stderr else "Unknown error"
            scan_job.completed_at = datetime.now(UTC)
            await db.commit()
            return

        # Parse OCSF JSON output
        findings_count = 0
        passed = 0
        failed = 0

        for json_file in Path(output_dir).glob("*.ocsf.json"):
            with open(json_file) as f:
                for line in f:
                    try:
                        finding_data = json.loads(line.strip())
                    except json.JSONDecodeError:
                        continue

                    check_id = finding_data.get("metadata", {}).get("product", {}).get("feature", {}).get("uid", "")
                    status_code = finding_data.get("status_code", "")
                    severity_text = finding_data.get("severity", "informational").lower()

                    f_status = (
                        FindingStatus.PASS
                        if status_code == "PASS"
                        else (FindingStatus.FAIL if status_code == "FAIL" else FindingStatus.MANUAL)
                    )
                    f_severity = (
                        FindingSeverity(severity_text)
                        if severity_text in FindingSeverity.__members__
                        else FindingSeverity.informational
                    )

                    if f_status == FindingStatus.PASS:
                        passed += 1
                    elif f_status == FindingStatus.FAIL:
                        failed += 1

                    finding = ProwlerFinding(
                        scan_job_id=scan_job.id,
                        check_id=check_id,
                        check_title=finding_data.get("message", "")[:500],
                        status=f_status,
                        severity=f_severity,
                        resource_uid=finding_data.get("resources", [{}])[0].get("uid", "")
                        if finding_data.get("resources")
                        else None,
                        resource_type=finding_data.get("resources", [{}])[0].get("type", "")
                        if finding_data.get("resources")
                        else None,
                        resource_region=finding_data.get("cloud", {}).get("region", ""),
                        isms_item_id=_prowler_mapping.get(check_id),
                        raw_json=finding_data,
                    )
                    db.add(finding)
                    findings_count += 1

        scan_job.status = ScanStatus.completed
        scan_job.total_checks = findings_count
        scan_job.passed = passed
        scan_job.failed = failed
        scan_job.completed_at = datetime.now(UTC)
        await db.commit()

    except Exception as e:
        scan_job.status = ScanStatus.failed
        scan_job.error_message = str(e)[:2000]
        scan_job.completed_at = datetime.now(UTC)
        await db.commit()
        raise
