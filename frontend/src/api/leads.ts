import apiClient from './client'
import type {
  Lead,
  LeadProfile,
  UploadResponse,
  ScoreResponse,
  DraftResponse,
  ApprovalResponse,
  GmailSendResponse,
  WorkflowSendResponse,
  ContactEmailResponse,
  LeadStatusResponse,
  SentEmail,
  CompanyDiscoverResponse,
  CompanyContactsResponse,
  ImportCompanyRequest,
  ImportCompaniesResponse,
  DiscoverLeadsResponse,
} from './types'

export async function getLeads(): Promise<Lead[]> {
  const { data } = await apiClient.get<Lead[]>('/api/leads')
  return data
}

export async function getLead(id: number): Promise<Lead> {
  const { data } = await apiClient.get<Lead>(`/api/leads/${id}`)
  return data
}

export async function getLeadProfile(id: number): Promise<LeadProfile> {
  const { data } = await apiClient.get<LeadProfile>(`/api/leads/${id}/profile`)
  return data
}

export async function uploadLeads(file: File): Promise<UploadResponse> {
  const formData = new FormData()
  formData.append('file', file)
  const { data } = await apiClient.post<UploadResponse>('/api/leads/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data
}

export async function scoreLead(id: number): Promise<ScoreResponse> {
  const { data } = await apiClient.post<ScoreResponse>(`/api/leads/${id}/score`)
  return data
}

export async function draftLead(id: number): Promise<DraftResponse> {
  const { data } = await apiClient.post<DraftResponse>(`/api/leads/${id}/draft`)
  return data
}

export async function qualifyLead(id: number): Promise<ApprovalResponse> {
  const { data } = await apiClient.post<ApprovalResponse>(`/api/leads/${id}/qualify`)
  return data
}

export async function fetchLeadContacts(id: number): Promise<LeadProfile> {
  const { data } = await apiClient.post<LeadProfile>(`/api/leads/${id}/fetch_contacts`)
  return data
}

export async function approveLead(id: number): Promise<GmailSendResponse> {
  const { data } = await apiClient.post<GmailSendResponse>(`/api/leads/${id}/approve`)
  return data
}

export async function unapproveLead(id: number): Promise<ApprovalResponse> {
  const { data } = await apiClient.post<ApprovalResponse>(`/api/leads/${id}/unapprove`)
  return data
}

export async function saveDraft(
  id: number,
  subject: string,
  body: string,
  toEmail: string,
): Promise<{ lead_id: number; status: string }> {
  const { data } = await apiClient.post<{ lead_id: number; status: string }>(
    `/api/leads/${id}/save_draft`,
    { subject, body, to_email: toEmail },
  )
  return data
}

export async function getLeadSentEmail(id: number): Promise<SentEmail> {
  const { data } = await apiClient.get<SentEmail>(`/api/leads/${id}/sent_email`)
  return data
}

export async function updateContactEmail(id: number, email: string): Promise<ContactEmailResponse> {
  const { data } = await apiClient.patch<ContactEmailResponse>(`/api/leads/${id}/contact_email`, {
    contact_email: email,
  })
  return data
}

export async function workflowSend(id: number, dryRun = false): Promise<WorkflowSendResponse> {
  const { data } = await apiClient.post<WorkflowSendResponse>(
    `/api/workflow/approve_and_send/${id}?dry_run=${dryRun}`
  )
  return data
}

export async function updateLeadStatus(id: number, status: string): Promise<LeadStatusResponse> {
  const { data } = await apiClient.patch<LeadStatusResponse>(`/api/leads/${id}/status`, { status })
  return data
}

export async function pullLeads(domains: string[]): Promise<{ new_leads_added: number }> {
  const { data } = await apiClient.post<{ new_leads_added: number }>('/api/leads/pull', {
    domains: domains,
  })
  return data
}

// Company Discovery Functions

export interface DiscoverCompaniesByIndustryRequest {
  industry: string
  country?: string
  city?: string
  source?: 'google' | 'google_maps'
  limit?: number
}

export async function discoverCompaniesByIndustry(
  request: DiscoverCompaniesByIndustryRequest
): Promise<CompanyDiscoverResponse> {
  const { data } = await apiClient.post<CompanyDiscoverResponse>('/api/companies/discover', {
    industry: request.industry,
    country: request.country || null,
    city: request.city || null,
    source: request.source || 'google_maps',
    limit: request.limit ?? 30,
  })
  return data
}

export async function getCompanyContacts(
  domain: string,
  source: string = 'hunter'
): Promise<CompanyContactsResponse> {
  const { data } = await apiClient.post<CompanyContactsResponse>(
    `/api/companies/${encodeURIComponent(domain)}/contacts`,
    { domain, source }
  )
  return data
}

export async function importCompaniesAsLeads(
  companies: ImportCompanyRequest[]
): Promise<ImportCompaniesResponse> {
  const { data } = await apiClient.post<ImportCompaniesResponse>('/api/leads/import', {
    companies,
  })
  return data
}

export async function discoverLeads(
  industry: string,
  keywords?: string[],
  company?: string,
): Promise<DiscoverLeadsResponse> {
  const { data } = await apiClient.post<DiscoverLeadsResponse>('/api/leads/discover', {
    industry,
    keywords: keywords?.length ? keywords : null,
    company: company || null,
  })
  return data
}
