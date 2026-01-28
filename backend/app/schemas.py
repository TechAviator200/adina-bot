from pydantic import BaseModel
from datetime import datetime
from typing import List, Optional


class HealthResponse(BaseModel):
    status: str
    timestamp: datetime


class ReadinessCheck(BaseModel):
    ok: bool
    error: Optional[str] = None


class ReadinessResponse(BaseModel):
    ready: bool
    database: ReadinessCheck
    knowledge_pack: ReadinessCheck
    gmail: ReadinessCheck


class LeadCreate(BaseModel):
    company: str
    industry: str
    location: Optional[str] = None
    employees: Optional[int] = None
    stage: Optional[str] = None
    website: Optional[str] = None
    notes: Optional[str] = None
    contact_name: Optional[str] = None
    contact_role: Optional[str] = None
    contact_email: Optional[str] = None


class LeadRead(BaseModel):
    id: int
    company: str
    industry: str
    location: Optional[str] = None
    employees: Optional[int] = None
    stage: Optional[str] = None
    website: Optional[str] = None
    notes: Optional[str] = None
    score: float
    score_reason: Optional[str] = None
    contact_name: Optional[str] = None
    contact_role: Optional[str] = None
    contact_email: Optional[str] = None
    email_subject: Optional[str] = None
    email_body: Optional[str] = None
    status: str
    source: Optional[str] = None
    source_url: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class UploadResponse(BaseModel):
    inserted: int
    skipped: int
    total_rows_parsed: int


class StatusCount(BaseModel):
    status: str
    count: int


class StatusResponse(BaseModel):
    total: int
    by_status: List[StatusCount]


class DraftResponse(BaseModel):
    lead_id: int
    subject: str
    body: str
    status: str


class ScoreResponse(BaseModel):
    lead_id: int
    score: float
    reasons: List[str]
    status: str


class ApprovalResponse(BaseModel):
    lead_id: int
    status: str


class ReplyDraftRequest(BaseModel):
    lead_id: int
    inbound_text: str


class ReplyDraftResponse(BaseModel):
    lead_id: int
    intent_label: str
    drafted_reply: str


class GmailConnectResponse(BaseModel):
    connected: bool
    email: Optional[str] = None
    auth_url: Optional[str] = None
    message: Optional[str] = None
    error: Optional[str] = None


class GmailConnectRequest(BaseModel):
    code: Optional[str] = None
    state: Optional[str] = None


class GmailSendResponse(BaseModel):
    success: bool
    lead_id: int
    message_id: Optional[str] = None
    error: Optional[str] = None


class BatchSendRequest(BaseModel):
    lead_ids: Optional[List[int]] = None
    limit: Optional[int] = 25


class BatchSendError(BaseModel):
    lead_id: int
    error: str


class BatchSendResponse(BaseModel):
    attempted: int
    sent: int
    skipped: int
    errors: List[BatchSendError]


class SentEmailRead(BaseModel):
    id: int
    lead_id: int
    to_email: str
    subject: str
    body: str
    gmail_message_id: Optional[str] = None
    sent_at: datetime

    class Config:
        from_attributes = True


class WorkflowSendResponse(BaseModel):
    lead_id: int
    status: str
    message_id: Optional[str] = None
    error: Optional[str] = None
    subject: Optional[str] = None
    body: Optional[str] = None


class ContactEmailUpdate(BaseModel):
    contact_email: str


class ContactEmailResponse(BaseModel):
    lead_id: int
    contact_email: str


class LeadStatusUpdate(BaseModel):
    status: str


class LeadStatusResponse(BaseModel):
    lead_id: int
    status: str


class PullLeadsRequest(BaseModel):
    domains: List[str]


class PullLeadsResponse(BaseModel):
    new_leads_added: int


class DiscoverLeadsRequest(BaseModel):
    industry: str
    keywords: Optional[List[str]] = None
    company: Optional[str] = None


class DiscoveredLead(BaseModel):
    company: str
    website: Optional[str] = None
    description: Optional[str] = None
    industry: str
    source_url: str
    score: float
    score_reasons: List[str]
    already_exists: bool = False


class DiscoverLeadsResponse(BaseModel):
    query_used: str
    total_found: int
    new_leads: int
    duplicates: int
    leads: List[DiscoveredLead]
    message: Optional[str] = None  # Maintenance or status message


# Company Discovery Schemas (Hunter Discover + Snov.io)

class CompanyDiscoverRequest(BaseModel):
    industry: str
    country: Optional[str] = None
    size: Optional[str] = None  # "1-10", "11-50", "51-200", "201-500", "500+"
    source: str = "both"  # "hunter", "snov", or "both"
    limit: int = 100


class DiscoveredCompany(BaseModel):
    name: str
    domain: Optional[str] = None
    description: Optional[str] = None
    industry: str
    size: Optional[str] = None
    location: Optional[str] = None
    source: str  # "hunter" or "snov"


class CompanyDiscoverResponse(BaseModel):
    total_found: int
    companies: List[DiscoveredCompany]
    message: Optional[str] = None


class CompanyContactsRequest(BaseModel):
    domain: str
    source: str = "hunter"  # "hunter" or "snov"


class ExecutiveContact(BaseModel):
    name: str
    title: Optional[str] = None
    email: Optional[str] = None
    linkedin_url: Optional[str] = None
    source: str  # "hunter" or "snov"


class CompanyContactsResponse(BaseModel):
    domain: str
    company_name: Optional[str] = None
    contacts: List[ExecutiveContact]
    message: Optional[str] = None


class ImportCompanyRequest(BaseModel):
    name: str
    domain: Optional[str] = None
    description: Optional[str] = None
    industry: str
    size: Optional[str] = None
    location: Optional[str] = None
    contact_name: Optional[str] = None
    contact_role: Optional[str] = None
    contact_email: Optional[str] = None
    source: str = "hunter"


class ImportCompaniesRequest(BaseModel):
    companies: List[ImportCompanyRequest]


class ImportCompaniesResponse(BaseModel):
    imported: int
    skipped: int
    leads: List[LeadRead]
