from datetime import date, datetime

from pydantic import BaseModel


# === Consent ===
class ConsentTemplateCreate(BaseModel):
    purpose: str
    legal_basis: str
    data_categories: str
    retention_period: str | None = None


class ConsentTemplateResponse(BaseModel):
    id: int
    purpose: str
    legal_basis: str
    data_categories: str
    retention_period: str | None
    is_active: bool
    created_at: datetime
    model_config = {"from_attributes": True}


class ConsentVersionCreate(BaseModel):
    content: str
    effective_date: date


class ConsentVersionResponse(BaseModel):
    id: int
    template_id: int
    version_number: int
    content: str
    effective_date: date
    is_published: bool
    created_at: datetime
    model_config = {"from_attributes": True}


# === DSR ===
class DSRCreate(BaseModel):
    request_type: str  # access/correction/deletion/suspension
    requester_name: str
    requester_contact: str | None = None
    requester_id_type: str | None = None
    description: str


class DSRUpdate(BaseModel):
    description: str | None = None
    requester_contact: str | None = None
    status: str | None = None  # only 'processing' allowed via PUT


class DSRResponse(BaseModel):
    id: int
    request_type: str
    requester_name: str
    requester_contact: str | None
    description: str
    status: str
    received_at: datetime
    due_date: date
    assigned_to: int | None
    result_description: str | None
    rejection_reason: str | None
    completed_at: datetime | None
    created_at: datetime
    model_config = {"from_attributes": True}


# === Destruction ===
class DestructionCreate(BaseModel):
    data_category: str
    data_description: str | None = None
    data_volume: str | None = None
    retention_basis: str | None = None
    retention_expiry: date
    scheduled_date: date
    method: str | None = None


class DestructionExecute(BaseModel):
    method: str
    actual_date: date


class DestructionVerify(BaseModel):
    verification_note: str | None = None
    certificate_url: str | None = None


class DestructionResponse(BaseModel):
    id: int
    data_category: str
    data_description: str | None
    data_volume: str | None
    retention_expiry: date
    scheduled_date: date
    actual_date: date | None
    method: str | None
    status: str
    handler_id: int | None
    verifier_id: int | None
    verified_at: datetime | None
    created_at: datetime
    model_config = {"from_attributes": True}


# === Third-party ===
class ThirdPartyCreate(BaseModel):
    company_name: str
    business_number: str | None = None
    contact_person: str | None = None
    contact_email: str | None = None
    purpose: str
    data_categories: str
    contract_start: date
    contract_end: date
    is_sub_delegated: bool = False
    parent_processor_id: int | None = None
    is_marketing_delegation: bool = False


class ThirdPartyResponse(BaseModel):
    id: int
    company_name: str
    business_number: str | None
    purpose: str
    contract_start: date
    contract_end: date
    is_sub_delegated: bool
    parent_processor_id: int | None
    is_active: bool
    created_at: datetime
    model_config = {"from_attributes": True}


# === Incident ===
class IncidentCreate(BaseModel):
    title: str
    severity: str
    description: str
    detected_at: datetime
    affected_subjects_count: int | None = None
    includes_sensitive_data: bool = False
    illegal_external_access: bool = False


class IncidentResponse(BaseModel):
    id: int
    title: str
    severity: str
    description: str
    status: str
    detected_at: datetime
    notification_deadline: datetime
    reportable_to_authority: bool
    affected_subjects_count: int | None
    initial_report_at: datetime | None
    subjects_notified_at: datetime | None
    created_at: datetime
    model_config = {"from_attributes": True}


class TimelineCreate(BaseModel):
    action: str
    description: str | None = None


class ReportAuthorityIn(BaseModel):
    type: str  # initial / supplemental


class NotifySubjectsIn(BaseModel):
    notified_at: datetime | None = None
    exception_reason: str | None = None
    website_notice_from: date | None = None
    website_notice_to: date | None = None


# === Corrective ===
class CorrectiveCreate(BaseModel):
    source: str  # external_audit/internal_review/prowler/config/other
    source_detail: str | None = None
    isms_item_id: int | None = None
    title: str
    description: str
    action_plan: str | None = None
    due_date: date
    assigned_to: int | None = None


class CorrectiveComplete(BaseModel):
    result: str
    evidence_id: int | None = None


class CorrectiveVerify(BaseModel):
    verification_note: str | None = None


class CorrectiveResponse(BaseModel):
    id: int
    source: str
    source_detail: str | None
    isms_item_id: int | None
    title: str
    description: str
    action_plan: str | None
    status: str
    due_date: date
    assigned_to: int | None
    result: str | None
    evidence_id: int | None
    completed_at: datetime | None
    verified_by: int | None
    verified_at: datetime | None
    created_at: datetime
    model_config = {"from_attributes": True}
