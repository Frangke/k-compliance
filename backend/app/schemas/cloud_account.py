"""Cloud account request/response schemas.

Authentication is IAM-role-based (no long-lived access keys):
  - instance_role: EC2 instance profile of the server running this app
  - assume_role: AssumeRole from the instance profile into a target role
                 in another AWS account (cross-account scanning)
"""

from typing import Literal

from pydantic import BaseModel, Field, model_validator

AuthType = Literal["instance_role", "assume_role"]


class CloudAccountCreate(BaseModel):
    provider: Literal["aws"] = "aws"
    account_id: str = Field(
        ..., min_length=12, max_length=12, pattern=r"^\d{12}$", description="12-digit AWS account number"
    )
    alias: str = Field(..., min_length=1, max_length=200)
    purpose: str | None = None
    admin_name: str | None = None
    admin_email: str | None = None

    # Credentials
    auth_type: AuthType = "instance_role"
    role_arn: str | None = Field(None, description="IAM Role ARN for AssumeRole")
    external_id: str | None = Field(None, description="ExternalId for AssumeRole (optional)")
    default_region: str = "ap-northeast-2"

    @model_validator(mode="after")
    def _check_credentials(self) -> "CloudAccountCreate":
        if self.auth_type == "assume_role":
            if not self.role_arn or not self.role_arn.startswith("arn:aws:iam::"):
                raise ValueError("assume_role에는 유효한 role_arn이 필요합니다 (arn:aws:iam::...)")
        return self


class CloudAccountUpdate(BaseModel):
    alias: str | None = None
    purpose: str | None = None
    admin_name: str | None = None
    admin_email: str | None = None
    is_active: bool | None = None

    # Credentials (optional; omit to keep existing)
    auth_type: AuthType | None = None
    role_arn: str | None = None
    external_id: str | None = None
    default_region: str | None = None


class CloudAccountResponse(BaseModel):
    id: int
    provider: str
    account_id: str
    alias: str
    purpose: str | None
    admin_name: str | None
    admin_email: str | None
    is_active: bool
    auth_type: AuthType
    role_arn: str | None = None
    external_id: str | None = None
    default_region: str | None = None
    credentials_last_updated: str | None = None


class CloudAccountVerifyResult(BaseModel):
    ok: bool
    message: str
    caller_arn: str | None = None
    account_id: str | None = None
