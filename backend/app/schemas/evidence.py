from datetime import date, datetime

from pydantic import BaseModel


class EvidenceResponse(BaseModel):
    id: int
    title: str
    description: str | None
    evidence_type: str
    file_name: str | None
    file_size: int | None
    file_hash: str | None
    external_url: str | None
    status: str
    valid_from: date | None
    valid_to: date | None
    version: int
    parent_id: int | None
    uploaded_by: int | None
    reviewed_by: int | None
    reviewed_at: datetime | None
    review_comment: str | None
    created_at: datetime
    model_config = {"from_attributes": True}


class EvidenceListResponse(BaseModel):
    items: list[EvidenceResponse]
    total: int


class EvidenceUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    valid_from: date | None = None
    valid_to: date | None = None


class ExternalLinkCreate(BaseModel):
    title: str
    description: str | None = None
    external_url: str
    valid_from: date | None = None
    valid_to: date | None = None


class ReviewAction(BaseModel):
    action: str  # approve / reject
    comment: str | None = None


class LinkItemsRequest(BaseModel):
    item_codes: list[str]
    relevance_note: str | None = None
