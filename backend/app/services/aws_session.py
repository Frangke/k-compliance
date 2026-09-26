"""boto3 session builder with IAM role / assume-role support."""

import uuid
from typing import Any

import boto3
from botocore.exceptions import ClientError, NoCredentialsError


def build_boto3_session(
    auth_type: str,
    region: str,
    role_arn: str | None = None,
    external_id: str | None = None,
    session_name: str | None = None,
) -> boto3.Session:
    """Return a boto3.Session configured for the given auth_type.

    - instance_role → default session (uses EC2 instance profile or env creds)
    - assume_role   → STS AssumeRole into target role
    """
    if auth_type == "instance_role":
        return boto3.Session(region_name=region)

    if auth_type == "assume_role":
        if not role_arn:
            raise ValueError("role_arn is required for assume_role")
        sts = boto3.client("sts", region_name=region)
        kwargs: dict[str, Any] = {
            "RoleArn": role_arn,
            "RoleSessionName": session_name or f"k-compliance-{uuid.uuid4().hex[:8]}",
            "DurationSeconds": 3600,
        }
        if external_id:
            kwargs["ExternalId"] = external_id
        resp = sts.assume_role(**kwargs)
        c = resp["Credentials"]
        return boto3.Session(
            aws_access_key_id=c["AccessKeyId"],
            aws_secret_access_key=c["SecretAccessKey"],
            aws_session_token=c["SessionToken"],
            region_name=region,
        )

    raise ValueError(f"Unsupported auth_type: {auth_type}")


def verify_aws_access(
    auth_type: str,
    region: str,
    role_arn: str | None = None,
    external_id: str | None = None,
    expected_account_id: str | None = None,
) -> dict:
    """Call STS GetCallerIdentity to verify credentials. Returns structured result."""
    try:
        session = build_boto3_session(auth_type, region, role_arn, external_id)
        sts = session.client("sts")
        identity = sts.get_caller_identity()
        caller_account = identity.get("Account")
        caller_arn = identity.get("Arn")

        if expected_account_id and caller_account != expected_account_id:
            return {
                "ok": False,
                "message": f"자격증명이 계정 {caller_account}에 속합니다 — 등록된 {expected_account_id}와 다릅니다",
                "caller_arn": caller_arn,
                "account_id": caller_account,
            }

        return {
            "ok": True,
            "message": "자격증명 검증 성공",
            "caller_arn": caller_arn,
            "account_id": caller_account,
        }
    except NoCredentialsError:
        return {"ok": False, "message": "자격증명을 찾을 수 없습니다 (EC2 instance profile 미설정?)"}
    except ClientError as e:
        return {"ok": False, "message": f"AWS 오류: {e.response.get('Error', {}).get('Message', str(e))}"}
    except Exception as e:
        return {"ok": False, "message": f"검증 실패: {str(e)[:200]}"}


def get_credentials_env(
    auth_type: str,
    region: str,
    role_arn: str | None = None,
    external_id: str | None = None,
) -> dict[str, str]:
    """Return a dict of AWS env vars suitable for passing to a subprocess (Prowler)."""
    if auth_type == "instance_role":
        # Subprocess inherits EC2 instance profile via IMDS; only region needs to be set
        return {"AWS_REGION": region, "AWS_DEFAULT_REGION": region}

    if auth_type == "assume_role":
        if not role_arn:
            raise ValueError("role_arn required")
        sts = boto3.client("sts", region_name=region)
        kwargs: dict[str, Any] = {
            "RoleArn": role_arn,
            "RoleSessionName": f"k-compliance-scan-{uuid.uuid4().hex[:8]}",
            "DurationSeconds": 3600,
        }
        if external_id:
            kwargs["ExternalId"] = external_id
        resp = sts.assume_role(**kwargs)
        c = resp["Credentials"]
        return {
            "AWS_ACCESS_KEY_ID": c["AccessKeyId"],
            "AWS_SECRET_ACCESS_KEY": c["SecretAccessKey"],
            "AWS_SESSION_TOKEN": c["SessionToken"],
            "AWS_REGION": region,
            "AWS_DEFAULT_REGION": region,
        }

    raise ValueError(f"Unsupported auth_type: {auth_type}")
