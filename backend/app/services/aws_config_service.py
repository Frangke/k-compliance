"""AWS Config conformance pack sync — boto3 read-only queries.

Background execution: `sync_conformance_pack(sync_job_id)` opens its own
AsyncSession. Never pass a request-scoped session in.
"""

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

import boto3
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import async_session
from app.models.aws_config import ConfigEvaluation, ConfigSyncJob
from app.models.prowler import CloudAccount, ScanStatus
from app.services.aws_session import build_boto3_session
from app.services.crypto import decrypt_json

logger = logging.getLogger("k-compliance.aws_config")

# Config rule → ISMS-P mapping
_config_mapping: dict[str, int] = {}


async def load_config_mapping(db: AsyncSession):
    global _config_mapping
    mapping_file = Path(__file__).parent.parent / "seeds" / "config_rule_mapping.json"
    if not mapping_file.exists():
        return
    with open(mapping_file) as f:
        raw = json.load(f)

    from app.models.isms import ISMSItem

    if isinstance(raw, dict):
        for rule_name, item_code in raw.items():
            result = await db.execute(select(ISMSItem.id).where(ISMSItem.code == item_code))
            item_id = result.scalar_one_or_none()
            if item_id:
                _config_mapping[rule_name] = item_id
    elif isinstance(raw, list):
        for entry in raw:
            rule_name = entry.get("config_rule_name") or entry.get("rule_name")
            item_code = entry.get("isms_item_code") or entry.get("isms_code")
            if rule_name and item_code:
                result = await db.execute(select(ISMSItem.id).where(ISMSItem.code == item_code))
                item_id = result.scalar_one_or_none()
                if item_id:
                    _config_mapping[rule_name] = item_id


async def sync_conformance_pack(sync_job_id: int) -> None:
    """Fetch Config conformance pack results in the background."""
    async with async_session() as db:
        try:
            await _run_sync(db, sync_job_id)
        except Exception as exc:
            logger.exception("sync_conformance_pack failed (sync_job_id=%s)", sync_job_id)
            # The inner _run_sync already tries to persist the error; this is a
            # defence-in-depth in case the inner session itself was broken.
            msg = f"{type(exc).__name__}: {exc}"[:2000]
            try:
                async with async_session() as db2:
                    job = (
                        await db2.execute(select(ConfigSyncJob).where(ConfigSyncJob.id == sync_job_id))
                    ).scalar_one_or_none()
                    if job and job.status not in (ScanStatus.completed, ScanStatus.cancelled):
                        job.status = ScanStatus.failed
                        job.error_message = msg
                        job.completed_at = datetime.now(UTC)
                        await db2.commit()
            except Exception:
                logger.exception("sync_conformance_pack recovery path also failed")


async def _run_sync(db: AsyncSession, sync_job_id: int) -> None:
    sync_job = (await db.execute(select(ConfigSyncJob).where(ConfigSyncJob.id == sync_job_id))).scalar_one_or_none()
    if not sync_job:
        logger.warning("sync_conformance_pack: sync_job %s disappeared", sync_job_id)
        return

    sync_job.status = ScanStatus.running
    sync_job.started_at = datetime.now(UTC)
    await db.commit()

    try:
        # Build boto3 session from associated cloud account (or instance role default)
        region = settings.S3_REGION
        if sync_job.cloud_account_id:
            acc = (
                await db.execute(select(CloudAccount).where(CloudAccount.id == sync_job.cloud_account_id))
            ).scalar_one_or_none()
            if not acc or not acc.is_active:
                raise Exception("클라우드 계정이 유효하지 않습니다")
            cred: dict = {}
            if acc.credentials:
                try:
                    cred = decrypt_json(acc.credentials)
                except Exception:
                    cred = {}
            region = acc.default_region or region
            session = build_boto3_session(
                auth_type=acc.auth_type or "instance_role",
                region=region,
                role_arn=cred.get("role_arn"),
                external_id=cred.get("external_id"),
            )
            client = session.client("config")
        else:
            client = boto3.client("config", region_name=region)
        pack_name = sync_job.conformance_pack

        compliant_count = 0
        non_compliant_count = 0
        total_count = 0

        # get_conformance_pack_compliance_details is NOT a paginable operation
        # in botocore. Paginate manually via NextToken.
        next_token: str | None = None
        while True:
            kwargs = {"ConformancePackName": pack_name}
            if next_token:
                kwargs["NextToken"] = next_token
            page = client.get_conformance_pack_compliance_details(**kwargs)
            for result in page.get("ConformancePackRuleComplianceList", []):
                rule_name = result.get("ConfigRuleName", "")
                compliance = result.get("ComplianceType", "NON_COMPLIANT")

                total_count += 1
                if compliance == "COMPLIANT":
                    compliant_count += 1
                else:
                    non_compliant_count += 1

                eval_rec = ConfigEvaluation(
                    sync_job_id=sync_job.id,
                    config_rule_name=rule_name,
                    compliance_type=compliance,
                    isms_item_id=_config_mapping.get(rule_name),
                    evaluated_at=datetime.now(UTC),
                )
                db.add(eval_rec)
            next_token = page.get("NextToken")
            if not next_token:
                break

        sync_job.status = ScanStatus.completed
        sync_job.total_rules = total_count
        sync_job.compliant = compliant_count
        sync_job.non_compliant = non_compliant_count
        sync_job.completed_at = datetime.now(UTC)
        await db.commit()

    except Exception as e:
        sync_job.status = ScanStatus.failed
        sync_job.error_message = str(e)[:2000]
        sync_job.completed_at = datetime.now(UTC)
        await db.commit()
        raise
