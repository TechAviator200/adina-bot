import { useState, useEffect } from 'react'
import { getOutreachTemplates } from '../api/inbox'
import { getLeads, fetchLeadContacts } from '../api/leads'
import { getGmailStatus, sendReply } from '../api/gmail'
import { useAgentLog } from '../hooks/useAgentLog'
import { useToast } from '../components/ui/Toast'
import type { Lead, OutreachEmailTemplate, ProfileContact } from '../api/types'
import Button from '../components/ui/Button'

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
  const [gmailConnected, setGmailConnected] = useState(false)
  const [sendingReply, setSendingReply] = useState(false)
  const [fetchingContacts, setFetchingContacts] = useState(false)
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
  }, [selectedLeadId])

  // Populate draft from template when template changes
  useEffect(() => {
    const t = templates.find((t) => t.id === selectedTemplateId)
    setDraftSubject(t?.subject ?? '')
    setDraftBody(t?.body ?? '')
  }, [selectedTemplateId, templates])

  const selectedLead = leads.find((l) => l.id === Number(selectedLeadId)) ?? null
  const leadContacts = selectedLead ? parseLeadContacts(selectedLead) : []
  const emailContacts = leadContacts.filter((c) => c.email)
  const hasSingleFallback = emailContacts.length === 0 && Boolean(selectedLead?.contact_email)
  const hasNoContacts = emailContacts.length === 0 && !hasSingleFallback

  // Effective recipient email
  const recipientEmail =
    selectedRecipient ||
    (emailContacts.length === 1 ? (emailContacts[0].email ?? '') : '') ||
    (hasSingleFallback ? (selectedLead?.contact_email ?? '') : '')

  const selectedTemplate = templates.find((t) => t.id === selectedTemplateId) ?? null
  const canSend = Boolean(
    selectedLeadId && recipientEmail && selectedTemplateId && draftBody && gmailConnected && !sendingReply
  )

  // Fetch contacts via Hunter.io and update this lead in local state
  async function handleFetchContacts() {
    if (!selectedLeadId) return
    setFetchingContacts(true)
    try {
      const profile = await fetchLeadContacts(Number(selectedLeadId))
      if (profile.contacts.length === 0) {
        addToast('No contacts found for this lead', 'error')
        return
      }
      // Patch the local leads state so the recipient dropdown recalculates
      const contactsJson = JSON.stringify(profile.contacts)
      setLeads((prev) =>
        prev.map((l) =>
          l.id === Number(selectedLeadId)
            ? { ...l, contacts_json: contactsJson, contact_email: profile.contact_email, contact_name: profile.contact_name }
            : l
        )
      )
      addToast(`Found ${profile.contacts.length} contact${profile.contacts.length !== 1 ? 's' : ''}`, 'success')
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to find contacts'
      addToast(msg, 'error')
    } finally {
      setFetchingContacts(false)
    }
  }

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

        {/* Recipient */}
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
            ) : hasNoContacts ? (
              <div className="px-3 py-2 bg-soft-navy/50 border border-warm-gray/20 rounded flex items-center justify-between">
                <span className="text-xs text-warm-gray">No contacts stored for this lead.</span>
                <button
                  onClick={handleFetchContacts}
                  disabled={fetchingContacts}
                  className="text-xs text-terracotta hover:underline disabled:opacity-50 shrink-0 ml-3"
                >
                  {fetchingContacts ? 'Looking up...' : 'Find Contacts'}
                </button>
              </div>
            ) : null}
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

        {/* Compose area — editable like a native email window */}
        {selectedTemplate && (
          <div className="bg-soft-navy border border-warm-gray/20 rounded-lg overflow-hidden">
            {/* Subject row */}
            <div className="flex items-center border-b border-warm-gray/15 px-4 py-2.5">
              <span className="text-xs text-warm-gray w-14 shrink-0">Subject</span>
              <input
                value={draftSubject}
                onChange={(e) => setDraftSubject(e.target.value)}
                className="flex-1 bg-transparent text-sm text-warm-cream outline-none placeholder:text-warm-gray/40"
                placeholder="Subject..."
              />
            </div>

            {/* To row */}
            <div className="flex items-center border-b border-warm-gray/15 px-4 py-2.5">
              <span className="text-xs text-warm-gray w-14 shrink-0">To</span>
              <span className="text-sm text-warm-cream/80">
                {recipientEmail || <span className="text-warm-gray/50 italic">select a recipient above</span>}
              </span>
            </div>

            {/* Body */}
            <textarea
              value={draftBody}
              onChange={(e) => setDraftBody(e.target.value)}
              rows={14}
              className="w-full bg-transparent px-4 py-3 text-sm text-warm-cream/90 leading-relaxed resize-none outline-none placeholder:text-warm-gray/40"
              placeholder="Start typing your email..."
            />

            {/* Actions */}
            <div className="px-4 py-3 border-t border-warm-gray/15 flex items-center gap-3">
              <Button
                size="sm"
                onClick={handleSendReply}
                disabled={!canSend}
              >
                {sendingReply ? 'Sending...' : 'Reply'}
              </Button>
              {!gmailConnected && (
                <span className="text-xs text-warm-gray">Gmail not connected</span>
              )}
              {gmailConnected && !recipientEmail && (
                <span className="text-xs text-warm-gray">Select a recipient above to send</span>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
