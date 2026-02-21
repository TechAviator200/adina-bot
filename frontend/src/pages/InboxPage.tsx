import { useState, useEffect } from 'react'
import { getOutreachTemplates } from '../api/inbox'
import { getLeads } from '../api/leads'
import { getGmailStatus, sendReply } from '../api/gmail'
import { useAgentLog } from '../hooks/useAgentLog'
import { useToast } from '../components/ui/Toast'
import type { Lead, OutreachEmailTemplate, ProfileContact } from '../api/types'
import Button from '../components/ui/Button'
import Card from '../components/ui/Card'

function parseLeadContacts(lead: Lead): ProfileContact[] {
  if (!lead.contacts_json) return []
  try {
    return JSON.parse(lead.contacts_json)
  } catch {
    return []
  }
}

export default function InboxPage() {
  const [leads, setLeads] = useState<Lead[]>([])
  const [selectedLeadId, setSelectedLeadId] = useState<number | ''>('')
  const [selectedRecipient, setSelectedRecipient] = useState<string>('')
  const [templates, setTemplates] = useState<OutreachEmailTemplate[]>([])
  const [selectedTemplateId, setSelectedTemplateId] = useState('')
  const [draftSubject, setDraftSubject] = useState('')
  const [draftBody, setDraftBody] = useState('')
  const [isReviewing, setIsReviewing] = useState(false)
  const [gmailConnected, setGmailConnected] = useState(false)
  const [sendingReply, setSendingReply] = useState(false)
  const { addLog } = useAgentLog()
  const { addToast } = useToast()

  useEffect(() => {
    getLeads().then(setLeads).catch(() => {})
    getOutreachTemplates().then(setTemplates).catch(() => {})
    getGmailStatus().then((s) => setGmailConnected(s.connected)).catch(() => {})
  }, [])

  // Reset recipient and draft when lead changes
  useEffect(() => {
    setSelectedRecipient('')
    setSelectedTemplateId('')
    setDraftSubject('')
    setDraftBody('')
    setIsReviewing(false)
  }, [selectedLeadId])

  // Populate draft from template when template changes
  useEffect(() => {
    const t = templates.find((t) => t.id === selectedTemplateId)
    setDraftSubject(t?.subject ?? '')
    setDraftBody(t?.body ?? '')
    setIsReviewing(false)
  }, [selectedTemplateId, templates])

  const selectedLead = leads.find((l) => l.id === Number(selectedLeadId)) ?? null
  const leadContacts = selectedLead ? parseLeadContacts(selectedLead) : []
  const emailContacts = leadContacts.filter((c) => c.email)
  const hasSingleFallback = emailContacts.length === 0 && Boolean(selectedLead?.contact_email)

  // Effective recipient email
  const recipientEmail =
    selectedRecipient ||
    (emailContacts.length === 1 ? (emailContacts[0].email ?? '') : '') ||
    (hasSingleFallback ? (selectedLead?.contact_email ?? '') : '')

  const selectedTemplate = templates.find((t) => t.id === selectedTemplateId) ?? null
  const canSend = Boolean(
    selectedLeadId && recipientEmail && selectedTemplateId && draftBody && gmailConnected && !sendingReply
  )

  async function handleSendReply() {
    if (!canSend || !selectedLeadId || !recipientEmail) return
    setSendingReply(true)
    try {
      const resp = await sendReply(Number(selectedLeadId), recipientEmail, draftSubject, draftBody)
      if (resp.success) {
        addToast('Reply sent via Gmail', 'success')
        addLog(`Reply sent to ${recipientEmail} for lead #${selectedLeadId}`)
        setSelectedTemplateId('')
        setDraftSubject('')
        setDraftBody('')
        setIsReviewing(false)
        setSelectedRecipient('')
      } else {
        addToast(`Send failed: ${resp.error || 'Unknown error'}`, 'error')
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Send failed'
      addToast(`Send reply failed: ${msg}`, 'error')
    } finally {
      setSendingReply(false)
    }
  }

  return (
    <div className="max-w-2xl">
      <h1 className="text-xl font-semibold text-warm-cream mb-4">Inbox</h1>

      {!gmailConnected && (
        <div className="mb-4 px-3 py-2 bg-warm-gray/10 border border-warm-gray/20 rounded-lg flex items-center justify-between">
          <span className="text-xs text-warm-gray">Gmail not connected — sending is disabled.</span>
          <a href="/settings" className="text-xs text-terracotta hover:underline">Connect in Settings →</a>
        </div>
      )}

      <div className="space-y-4">
        {/* Lead */}
        <div>
          <label className="block text-xs text-warm-gray mb-1">Lead</label>
          <select
            value={selectedLeadId}
            onChange={(e) => setSelectedLeadId(e.target.value ? Number(e.target.value) : '')}
            className="w-full bg-soft-navy border border-warm-gray/30 rounded px-3 py-2 text-sm text-warm-cream"
          >
            <option value="">Select a lead...</option>
            {leads.map((l) => (
              <option key={l.id} value={l.id}>
                #{l.id} — {l.company}
              </option>
            ))}
          </select>
        </div>

        {/* Recipient — populated from lead's contacts */}
        {selectedLeadId && (
          <div>
            <label className="block text-xs text-warm-gray mb-1">
              Recipient <span className="text-terracotta">*</span>
            </label>
            {emailContacts.length > 1 ? (
              <select
                value={selectedRecipient}
                onChange={(e) => setSelectedRecipient(e.target.value)}
                className="w-full bg-soft-navy border border-warm-gray/30 rounded px-3 py-2 text-sm text-warm-cream"
              >
                <option value="">Select a contact...</option>
                {emailContacts.map((c, i) => (
                  <option key={i} value={c.email!}>
                    {c.name}{c.title ? ` (${c.title})` : ''} — {c.email}
                  </option>
                ))}
              </select>
            ) : emailContacts.length === 1 ? (
              <div className="px-3 py-2 bg-soft-navy border border-warm-gray/30 rounded">
                <p className="text-sm text-warm-cream">
                  {emailContacts[0].name}
                  {emailContacts[0].title && (
                    <span className="text-warm-gray"> ({emailContacts[0].title})</span>
                  )}
                </p>
                <p className="text-xs text-warm-gray mt-0.5">{emailContacts[0].email}</p>
              </div>
            ) : hasSingleFallback ? (
              <div className="px-3 py-2 bg-soft-navy border border-warm-gray/30 rounded">
                {selectedLead?.contact_name && (
                  <p className="text-sm text-warm-cream">{selectedLead.contact_name}</p>
                )}
                <p className="text-xs text-warm-gray mt-0.5">{selectedLead?.contact_email}</p>
              </div>
            ) : (
              <p className="text-xs text-warm-gray px-3 py-2 bg-soft-navy/50 border border-warm-gray/20 rounded">
                No contacts stored for this lead.
              </p>
            )}
          </div>
        )}

        {/* Outreach Template */}
        {selectedLeadId && (
          <div>
            <label className="block text-xs text-warm-gray mb-1">Outreach Template</label>
            <select
              value={selectedTemplateId}
              onChange={(e) => setSelectedTemplateId(e.target.value)}
              className="w-full bg-soft-navy border border-warm-gray/30 rounded px-3 py-2 text-sm text-warm-cream"
            >
              <option value="">Select a template...</option>
              {templates.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name}
                </option>
              ))}
            </select>
          </div>
        )}

        {/* Draft preview / edit */}
        {selectedTemplate && (
          <Card>
            <div className="mb-3">
              <span className="text-xs text-warm-gray block mb-1">Subject</span>
              {isReviewing ? (
                <input
                  value={draftSubject}
                  onChange={(e) => setDraftSubject(e.target.value)}
                  className="w-full bg-soft-navy border border-warm-gray/30 rounded px-3 py-1.5 text-sm text-warm-cream"
                />
              ) : (
                <p className="text-sm text-warm-cream font-medium">{draftSubject}</p>
              )}
            </div>
            <div>
              <span className="text-xs text-warm-gray block mb-1">Body</span>
              {isReviewing ? (
                <textarea
                  value={draftBody}
                  onChange={(e) => setDraftBody(e.target.value)}
                  rows={10}
                  className="w-full bg-soft-navy border border-warm-gray/30 rounded px-3 py-2 text-sm text-warm-cream resize-none"
                />
              ) : (
                <p className="text-sm whitespace-pre-wrap text-warm-cream">{draftBody}</p>
              )}
            </div>

            <div className="mt-4 pt-4 border-t border-warm-gray/10 flex items-center gap-3 flex-wrap">
              <Button
                size="sm"
                variant="secondary"
                onClick={() => setIsReviewing(!isReviewing)}
              >
                {isReviewing ? 'Done Editing' : 'Review Draft'}
              </Button>
              <Button
                size="sm"
                onClick={handleSendReply}
                disabled={!canSend}
              >
                {sendingReply ? 'Sending...' : 'Reply'}
              </Button>
              {gmailConnected && recipientEmail && (
                <span className="text-xs text-warm-gray">→ {recipientEmail}</span>
              )}
              {gmailConnected && !recipientEmail && (
                <span className="text-xs text-warm-gray">Select a recipient above</span>
              )}
            </div>
          </Card>
        )}
      </div>
    </div>
  )
}
