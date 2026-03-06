import apiClient from './client'
import type {
  EmailAccountsStatusResponse,
  ConnectSmtpRequest,
  ConnectSmtpResponse,
  GeneralSendResponse,
} from './types'

export async function getEmailAccountsStatus(): Promise<EmailAccountsStatusResponse> {
  const { data } = await apiClient.get<EmailAccountsStatusResponse>('/api/email-accounts/status')
  return data
}

export async function setActiveAccount(accountId: number): Promise<{ success: boolean; active_account_id: number; email: string }> {
  const { data } = await apiClient.post('/api/email-accounts/set-active', { account_id: accountId })
  return data
}

export async function disconnectAccount(accountId: number): Promise<{ success: boolean }> {
  const { data } = await apiClient.post('/api/email-accounts/disconnect', { account_id: accountId })
  return data
}

export async function connectSmtp(req: ConnectSmtpRequest): Promise<ConnectSmtpResponse> {
  const { data } = await apiClient.post<ConnectSmtpResponse>('/api/email-accounts/connect/smtp', req)
  return data
}

export async function getGoogleConnectUrl(): Promise<{ url?: string; error?: string }> {
  const { data } = await apiClient.get<{ url?: string; error?: string }>('/api/email-accounts/connect/google/start')
  return data
}

export async function getOutlookConnectUrl(): Promise<{ url?: string; error?: string }> {
  const { data } = await apiClient.get<{ url?: string; error?: string }>('/api/email-accounts/connect/outlook/start')
  return data
}

export async function sendEmailGeneral(params: {
  to: string
  subject: string
  body: string
  from_account_id?: number
}): Promise<GeneralSendResponse> {
  const { data } = await apiClient.post<GeneralSendResponse>('/api/email/send', params)
  return data
}

export async function replyEmailGeneral(params: {
  lead_id: number
  to: string
  subject: string
  body: string
  from_account_id?: number
}): Promise<GeneralSendResponse> {
  const { data } = await apiClient.post<GeneralSendResponse>('/api/email/reply', params)
  return data
}
