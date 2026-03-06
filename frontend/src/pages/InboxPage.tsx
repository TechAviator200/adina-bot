import { useState, useEffect, useRef, useContext } from 'react'
import { useSearchParams, useNavigate } from 'react-router-dom'
import { getOutreachTemplates } from '../api/inbox'
import { getLeads, fetchLeadContacts, saveDraft } from '../api/leads'
import { getEmailAccountsStatus, replyEmailGeneral } from '../api/emailAccounts'
import { useAgentLog } from '../hooks/useAgentLog'
import { useToast } from '../components/ui/Toast'
import { LeadProfileContext } from '../context/LeadProfileContext'
import type { Lead, OutreachEmailTemplate, ProfileContact, EmailAccount } from '../api/types'
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
  const [searchParams, setSearchParams] = useSearchParams()
  const navigate = useNavigate()
  const { setSelectedLeadId: setProfileLeadId } = useContext(LeadProfileContext)
  const [leads, setLeads] = useState<Lead[]>([])
  const [selectedLeadId, setSelectedLeadId] = useState<number | ''>('')
  const [selectedRecipient, setSelectedRecipient] = useState<string>('')
  const [templates, setTemplates] = useState<OutreachEmailTemplate[]>([])
  const [selectedTemplateId, setSelectedTemplateId] = useState('')
  const [draftSubject, setDraftSubject] = useState('')
  const [draftBody, setDraftBody] = useState('')
  const [emailAccounts, setEmailAccounts] = useState<EmailAccount[]>([])
  const [activeAccount, setActiveAccount] = useState<EmailAccount | null>(null)
  const [selectedAccountId, setSelectedAccountId] = useState<number | null>(null)
  const [sendingReply, setSendingReply] = useState(false)
  const [savingDraft, setSavingDraft] = useState(false)
  const [fetchingContacts, setFetchingContacts] = useState(false)
  const { addLog } = useAgentLog()
  const { addToast } = useToast()
  const pendingEmailRef = useRef<string | null>(null)
  const pendingDraftRef = useRef<{ subject: string; body: string } | null>(null)

  const hasConnectedAccount = emailAccounts.length > 0

  useEffect(() => {
    Promise.all([
      getLeads(),
      getOutreachTemplates(),
      getEmailAccountsStatus(),
    ]).then(([fetchedLeads, fetchedTemplates, accountsStatus]) => {
      setLeads(fetchedLeads)
      setTemplates(fetchedTemplates)
      setEmailAccounts(accountsStatus.accounts)
      setActiveAccount(accountsStatus.active_account)
      if (accountsStatus.active_account) {
        setSelectedAccountId(accountsStatus.active_account.id)
      } else if (accountsStatus.accounts.length > 0) {
        setSelectedAccountId(accountsStatus.accounts[0].id)
      }

      const paramLeadId = searchParams.get('leadId')
      const paramEmail = searchParams.get('email')
      if (paramLeadId) {
        const id = Number(paramLeadId)
        const lead = fetchedLeads.find((l) => l.id === id)
        if (lead) {
          if (paramEmail) {
            pendingEmailRef.current = decodeURIComponent(paramEmail)
          } else if (lead.contact_email) {
            pendingEmailRef.current = lead.contact_email
          }
          if (lead.email_subject || lead.email_body) {
            pendingDraftRef.current = {
              subject: lead.email_subject ?? '',
              body: lead.email_body ?? '',
            }
          }
          setSelectedLeadId(id)
        }
      }
      if (paramLeadId || paramEmail) setSearchParams({}, { replace: true })
    }).catch(() => {})
  }, [])

  useEffect(() => {
    const pendingEmail = pendingEmailRef.current
    const pendingDraft = pendingDraftRef.current
    pendingEmailRef.current = null
    pendingDraftRef.current = null

    setSelectedRecipient(pendingEmail ?? '')
    setSelectedTemplateId('')

    if (pendingDraft) {
      setDraftSubject(pendingDraft.subject)
      setDraftBody(pendingDraft.body)
    } else {
      setDraftSubject('')
      setDraftBody('')
    }
  }, [selectedLeadId])

  useEffect(() => {
    setProfileLeadId(selectedLeadId ? Number(selectedLeadId) : null)
    return () => { setProfileLeadId(null) }
  }, [selectedLeadId])

  useEffect(() => {
    if (!selectedTemplateId) return
    const t = templates.find((t) => t.id === selectedTemplateId)
    if (t) {
      setDraftSubject(t.subject)
      setDraftBody(t.body)
    }
  }, [selectedTemplateId, templates])

  const selectedLead = leads.find((l) => l.id === Number(selectedLeadId)) ?? null
  const leadContacts = selectedLead ? parseLeadContacts(selectedLead) : []
  const emailContacts = leadContacts.filter((c) => c.email)
  const hasSingleFallback = emailContacts.length === 0 && Boolean(selectedLead?.contact_email)
  const hasNoContacts = emailContacts.length === 0 && !hasSingleFallback

  const recipientEmail =
    selectedRecipient ||
    (emailContacts.length === 1 ? (emailContacts[0].email ?? '') : '') ||
    (hasSingleFallback ? (selectedLead?.contact_email ?? '') : '')

  const selectedTemplate = templates.find((t) => t.id === selectedTemplateId) ?? null
  const showCompose = Boolean(selectedTemplate || draftSubject || draftBody)

  // Effective sending account
  const sendingAccount = emailAccounts.find((a) => a.id === selectedAccountId) ?? activeAccount

  const canSend = Boolean(
    selectedLeadId && recipientEmail && draftBody && sendingAccount && !sendingReply
  )
  const canSaveDraft = Boolean(
    selectedLeadId && recipientEmail && draftBody && !savingDraft
  )

  async function handleFetchContacts() {
    if (!selectedLeadId) return
    setFetchingContacts(true)
    try {
      const profile = await fetchLeadContacts(Number(selectedLeadId))
      if (profile.contacts.length === 0) {
        addToast('No contacts found for this lead', 'error')
        return
      }
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
      const resp = await replyEmailGeneral({
        lead_id: Number(selectedLeadId),
        to: recipientEmail,
        subject: draftSubject,
        body: draftBody,
        from_account_id: sendingAccount?.id,
      })
      if (resp.success) {
        addToast(`Email sent via ${resp.provider ?? 'connected account'}`, 'success')
        addLog(`Email sent to ${recipientEmail} for lead #${selectedLeadId}`)
        setSelectedTemplateId('')
        setDraftSubject('')
        setDraftBody('')
        setSelectedRecipient('')
        setSelectedLeadId('')
      } else {
        addToast(`Send failed: ${resp.error || 'Unknown error'}`, 'error')
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Send failed'
      addToast(`Send failed: ${msg}`, 'error')
    } finally {
      setSendingReply(false)
    }
  }

  async function handleSaveDraft() {
    if (!canSaveDraft || !selectedLeadId || !recipientEmail) return
    setSavingDraft(true)
    try {
      await saveDraft(Number(selectedLeadId), draftSubject, draftBody, recipientEmail)
      addToast('Draft saved — lead moved to Drafted', 'success')
      addLog(`Draft saved for lead #${selectedLeadId} → ${recipientEmail}`)
      navigate('/leads')
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Save failed'
      addToast(`Save draft failed: ${msg}`, 'error')
    } finally {
      setSavingDraft(false)
    }
  }

  return (
    <div className="max-w-2xl">
      <h1 className="text-xl font-semibold text-warm-cream mb-4">Inbox</h1>

      {!hasConnectedAccount && (
        <div className="mb-4 px-3 py-2 bg-warm-gray/10 border border-warm-gray/20 rounded-lg flex items-center justify-between">
          <span className="text-xs text-warm-gray">No sending account connected — sending is disabled.</span>
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
                {emailContacts[0].phone && (
                  <p className="text-xs text-warm-gray/70 mt-0.5">{emailContacts[0].phone}</p>
                )}
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

        {/* From account selector (shown when multiple accounts) */}
        {selectedLeadId && hasConnectedAccount && emailAccounts.length > 1 && (
          <div>
            <label className="block text-xs text-warm-gray mb-1">Send From</label>
            <select
              value={selectedAccountId ?? ''}
              onChange={(e) => setSelectedAccountId(e.target.value ? Number(e.target.value) : null)}
              className="w-full bg-soft-navy border border-warm-gray/30 rounded px-3 py-2 text-sm text-warm-cream"
            >
              {emailAccounts.map((acc) => (
                <option key={acc.id} value={acc.id}>
                  {acc.email_address} ({acc.provider}){acc.is_active ? ' — active' : ''}
                </option>
              ))}
            </select>
          </div>
        )}

        {/* Outreach Template */}
        {selectedLeadId && (
          <div>
            <label className="block text-xs text-warm-gray mb-1">
              Outreach Template
              {(draftSubject || draftBody) && !selectedTemplateId && (
                <span className="ml-2 text-terracotta/70 normal-case font-normal">(saved draft loaded)</span>
              )}
            </label>
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

        {/* Compose area */}
        {showCompose && (
          <div className="bg-soft-navy border border-warm-gray/20 rounded-lg overflow-hidden">
            {/* From row */}
            {sendingAccount && (
              <div className="flex items-center border-b border-warm-gray/15 px-4 py-2.5">
                <span className="text-xs text-warm-gray w-14 shrink-0">From</span>
                <span className="text-sm text-warm-cream/80">{sendingAccount.email_address}</span>
                <span className="ml-2 text-[10px] text-warm-gray/60">({sendingAccount.provider})</span>
              </div>
            )}

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
                {sendingReply ? 'Sending...' : 'Send'}
              </Button>
              <Button
                size="sm"
                variant="secondary"
                onClick={handleSaveDraft}
                disabled={!canSaveDraft}
              >
                {savingDraft ? 'Saving...' : 'Save Draft'}
              </Button>
              {!hasConnectedAccount && (
                <span className="text-xs text-warm-gray">No account connected</span>
              )}
              {hasConnectedAccount && !recipientEmail && (
                <span className="text-xs text-warm-gray">Select a recipient above to send</span>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
