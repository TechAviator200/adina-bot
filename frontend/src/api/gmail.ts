import apiClient from './client'
import type { GmailStatus, GmailSendResponse } from './types'

export interface AppConfig {
  demo_mode: boolean
  oauth_redirect_uri: string
}

export async function getAppConfig(): Promise<AppConfig> {
  const { data } = await apiClient.get<AppConfig>('/api/config')
  return data
}

export async function getGmailStatus(): Promise<GmailStatus> {
  const { data } = await apiClient.get<GmailStatus>('/api/gmail/status')
  return data
}

export async function connectGmail(): Promise<GmailStatus> {
  // Use the DB-backed OAuth endpoint which returns {url} or {error}
  const { data } = await apiClient.get<{ url?: string; error?: string }>('/api/gmail/auth/start')
  return {
    connected: false,
    email: null,
    auth_url: data.url ?? null,
    message: null,
    error: data.error ?? null,
  }
}

export async function disconnectGmail(): Promise<{ success: boolean }> {
  const { data } = await apiClient.post<{ success: boolean }>('/api/gmail/disconnect')
  return data
}

export async function sendEmail(leadId: number): Promise<GmailSendResponse> {
  const { data } = await apiClient.post<GmailSendResponse>(`/api/gmail/send/${leadId}`)
  return data
}

export async function sendReply(
  leadId: number,
  toEmail: string,
  subject: string,
  body: string,
): Promise<GmailSendResponse> {
  const { data } = await apiClient.post<GmailSendResponse>('/api/gmail/send_reply', {
    lead_id: leadId,
    to_email: toEmail,
    subject,
    body,
  })
  return data
}
