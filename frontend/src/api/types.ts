export interface Lead {
  id: number
  company: string
  industry: string
  location: string | null
  employees: number | null
  stage: string | null
  website: string | null
  notes: string | null
  score: number
  score_reason: string | null
  contact_name: string | null
  contact_role: string | null
  contact_email: string | null
  email_subject: string | null
  email_body: string | null
  status: string
  source: string | null
  source_url: string | null
  created_at: string
  phone: string | null
  linkedin_url: string | null
  contacts_json: string | null  // JSON string: ProfileContact[]
}

export interface ProfileContact {
  name: string
  title: string | null
  email: string | null
  linkedin_url: string | null
  source: string | null
}

export interface LeadProfile {
  id: number
  company: string
  website: string | null
  phone: string | null
  location: string | null
  description: string | null
  linkedin_url: string | null
  contacts: ProfileContact[]
  status: string
  source: string | null
  industry: string
  contact_name: string | null
  contact_email: string | null
}

export interface UploadResponse {
  inserted: number
  skipped: number
  total_rows_parsed: number
}

export interface StatusCount {
  status: string
  count: number
}

export interface StatusResponse {
  total: number
  by_status: StatusCount[]
}

export interface DraftResponse {
  lead_id: number
  subject: string
  body: string
  status: string
}

export interface ScoreResponse {
  lead_id: number
  score: number
  reasons: string[]
  status: string
}

export interface ApprovalResponse {
  lead_id: number
  status: string
}

export interface ReplyDraftResponse {
  lead_id: number
  intent_label: string
  drafted_reply: string
}

export interface GmailStatus {
  connected: boolean
  email: string | null
  auth_url: string | null
  message: string | null
  error: string | null
}

export interface GmailSendResponse {
  success: boolean
  lead_id: number
  message_id: string | null
  error: string | null
}

export interface SentEmail {
  id: number
  lead_id: number
  to_email: string
  subject: string
  body: string
  gmail_message_id: string | null
  sent_at: string
}

export interface WorkflowSendResponse {
  lead_id: number
  status: string
  message_id: string | null
  error: string | null
  subject: string | null
  body: string | null
}

export interface ContactEmailResponse {
  lead_id: number
  contact_email: string
}

export interface LeadStatusResponse {
  lead_id: number
  status: string
}

export interface OutreachTemplate {
  intent: string
  tone: string
  template: string
  cta: string
}

// Outreach email templates from the ADINA playbook PDF
export interface OutreachEmailTemplate {
  id: string
  name: string
  subject: string
  body: string
}

// Company Discovery Types

export interface DiscoveredCompany {
  name: string
  domain: string | null
  website_url: string | null
  phone: string | null
  location: string | null
  description: string | null
  source: string
}

export interface CompanyDiscoverResponse {
  companies: DiscoveredCompany[]
  cached: boolean
  message: string | null
}

export interface ExecutiveContact {
  name: string
  title: string | null
  email: string | null
  linkedin_url: string | null
  source: string
}

export interface CompanyContactsResponse {
  domain: string
  company_name: string | null
  contacts: ExecutiveContact[]
  message: string | null
}

export interface ImportCompanyRequest {
  name: string
  domain: string | null
  description: string | null
  industry: string
  size: string | null
  location: string | null
  phone: string | null
  website_url: string | null
  contact_name: string | null
  contact_role: string | null
  contact_email: string | null
  contacts: ProfileContact[] | null  // Full contacts list for contacts_json
  source: string
}

export interface ImportCompaniesResponse {
  imported: number
  skipped: number
  leads: Lead[]
}
