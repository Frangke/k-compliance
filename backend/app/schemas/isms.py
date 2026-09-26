from datetime import datetime

from pydantic import BaseModel


class ChecklistBrief(BaseModel):
    id: int
    question: str
    sort_order: int
    model_config = {"from_attributes": True}


class ItemResponse(BaseModel):
    id: int
    code: str
    name: str
    description: str | None
    required_evidence: str | None
    has_prowler_checks: bool
    prowler_check_count: int
    has_config_rules: bool
    sort_order: int
    subdomain_code: str | None = None
    domain_code: str | None = None
    # aggregated (optional, filled in detail)
    evidence_count: int = 0
    checklist_total: int = 0
    model_config = {"from_attributes": True}


class SubdomainResponse(BaseModel):
    id: int
    code: str
    name: str
    description: str | None
    items: list[ItemResponse] = []
    model_config = {"from_attributes": True}


class DomainResponse(BaseModel):
    id: int
    code: str
    name: str
    description: str | None
    subdomains: list[SubdomainResponse] = []
    model_config = {"from_attributes": True}


class ItemListResponse(BaseModel):
    items: list[ItemResponse]
    total: int


class AssignmentResponse(BaseModel):
    id: int
    user_id: int
    username: str | None = None
    name: str | None = None
    role_in_item: str
    assigned_at: datetime
    model_config = {"from_attributes": True}


class AssignmentCreate(BaseModel):
    user_id: int
    role_in_item: str = "owner"


class ComplianceSummary(BaseModel):
    domain_code: str
    domain_name: str
    total: int
    compliant: int
    partial: int
    non_compliant: int
    not_assessed: int
    rate: float
