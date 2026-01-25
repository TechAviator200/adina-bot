import apiClient from './client'
import type { ReplyDraftResponse, SentEmail, OutreachTemplate } from './types'

export async function draftReply(leadId: number, inboundText: string): Promise<ReplyDraftResponse> {
  const { data } = await apiClient.post<ReplyDraftResponse>('/api/reply/draft', {
    lead_id: leadId,
    inbound_text: inboundText,
  })
  return data
}

export async function getSentEmails(): Promise<SentEmail[]> {
  const { data } = await apiClient.get<SentEmail[]>('/api/sent')
  return data
}

export async function getTemplates(): Promise<OutreachTemplate[]> {
  const { data } = await apiClient.get<OutreachTemplate[]>('/api/templates')
  return data
}
