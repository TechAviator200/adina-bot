import { useState, useEffect } from 'react'
import { draftReply, getOutreachTemplates } from '../api/inbox'
import { getLeads } from '../api/leads'
import { useAgentLog } from '../hooks/useAgentLog'
import { useToast } from '../components/ui/Toast'
import type { Lead, ReplyDraftResponse, OutreachEmailTemplate, ProfileContact } from '../api/types'
import Button from '../components/ui/Button'
import Badge from '../components/ui/Badge'
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
  const [selectedTemplate, setSelectedTemplate] = useState('')
  const [inboundText, setInboundText] = useState('')
  const [result, setResult] = useState<ReplyDraftResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const { addLog } = useAgentLog()
  const { addToast } = useToast()

  useEffect(() => {
    getLeads().then(setLeads).catch(() => {})
    getOutreachTemplates().then(setTemplates).catch(() => {})
  }, [])

  // Reset recipient when lead changes
  useEffect(() => {
    setSelectedRecipient('')
    setResult(null)
  }, [selectedLeadId])

  const selectedLead = leads.find((l) => l.id === Number(selectedLeadId)) ?? null
  const leadContacts = selectedLead ? parseLeadContacts(selectedLead) : []
  const emailContacts = leadContacts.filter((c) => c.email)

  // Determine effective contacts list: from contacts_json, or fall back to contact_email
  const hasMultipleContacts = emailContacts.length > 1
  const hasSingleFallback = emailContacts.length === 0 && selectedLead?.contact_email
  const recipientRequired = Boolean(selectedLeadId) && hasMultipleContacts
  const canClassify = Boolean(selectedLeadId) && inboundText.trim().length > 0
    && (!recipientRequired || Boolean(selectedRecipient))

  async function handleClassify() {
    if (!canClassify || !selectedLeadId) return
    setLoading(true)
    setResult(null)
    try {
      const resp = await draftReply(Number(selectedLeadId), inboundText)
      setResult(resp)
      addLog(`Classified reply for lead #${selectedLeadId}: intent="${resp.intent_label}"`)
      addToast(`Classified: ${resp.intent_label}`, 'success')
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed'
      addLog(`Classify error: ${msg}`)
      addToast(`Classify failed: ${msg}`, 'error')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="max-w-2xl">
      <h1 className="text-xl font-semibold text-warm-cream mb-4">Inbox</h1>

      <div className="space-y-3">
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

        {/* Recipient dropdown — required when lead has multiple contacts */}
        {selectedLeadId && (
          <div>
            <label className="block text-xs text-warm-gray mb-1">
              Recipient {recipientRequired && <span className="text-terracotta">*</span>}
            </label>
            {hasMultipleContacts ? (
              <>
                <select
                  value={selectedRecipient}
                  onChange={(e) => setSelectedRecipient(e.target.value)}
                  className="w-full bg-soft-navy border border-warm-gray/30 rounded px-3 py-2 text-sm text-warm-cream"
                >
                  <option value="">Select recipient...</option>
                  {emailContacts.map((c, i) => (
                    <option key={i} value={c.email!}>
                      {c.name}{c.title ? ` (${c.title})` : ''} — {c.email}
                    </option>
                  ))}
                </select>
                {!selectedRecipient && (
                  <p className="text-xs text-warm-gray mt-1">
                    A recipient is required before classifying.
                  </p>
                )}
              </>
            ) : hasSingleFallback ? (
              <p className="text-xs text-warm-cream px-3 py-2 bg-soft-navy border border-warm-gray/30 rounded">
                {selectedLead?.contact_name && `${selectedLead.contact_name} — `}{selectedLead?.contact_email}
              </p>
            ) : emailContacts.length === 1 ? (
              <p className="text-xs text-warm-cream px-3 py-2 bg-soft-navy border border-warm-gray/30 rounded">
                {emailContacts[0].name}{emailContacts[0].title ? ` (${emailContacts[0].title})` : ''} — {emailContacts[0].email}
              </p>
            ) : (
              <p className="text-xs text-warm-gray px-3 py-2">No contacts stored for this lead.</p>
            )}
          </div>
        )}

        <div>
          <label className="block text-xs text-warm-gray mb-1">Outreach Template</label>
          <select
            value={selectedTemplate}
            onChange={(e) => setSelectedTemplate(e.target.value)}
            className="w-full bg-soft-navy border border-warm-gray/30 rounded px-3 py-2 text-sm text-warm-cream"
          >
            <option value="">Select a template...</option>
            {templates.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name}
              </option>
            ))}
          </select>
          {selectedTemplate && (
            <div className="mt-2 p-3 bg-soft-navy/50 rounded border border-warm-gray/10">
              <p className="text-xs text-warm-gray mb-1">Subject: <span className="text-warm-cream">{templates.find((t) => t.id === selectedTemplate)?.subject}</span></p>
              <p className="text-xs text-warm-gray whitespace-pre-wrap mt-2">{templates.find((t) => t.id === selectedTemplate)?.body}</p>
            </div>
          )}
        </div>

        <div>
          <label className="block text-xs text-warm-gray mb-1">Inbound email text</label>
          <textarea
            value={inboundText}
            onChange={(e) => setInboundText(e.target.value)}
            rows={5}
            className="w-full bg-soft-navy border border-warm-gray/30 rounded px-3 py-2 text-sm text-warm-cream resize-none"
            placeholder="Paste the inbound email text here..."
          />
        </div>

        <Button onClick={handleClassify} disabled={loading || !canClassify}>
          {loading ? 'Classifying...' : 'Classify & Draft Reply'}
        </Button>
        {recipientRequired && !selectedRecipient && (
          <p className="text-xs text-terracotta">Select a recipient to proceed.</p>
        )}
      </div>

      {result && (
        <Card className="mt-6">
          <div className="flex items-center gap-2 mb-3">
            <span className="text-xs text-warm-gray font-medium">Intent:</span>
            <Badge status={result.intent_label} />
          </div>
          <div>
            <span className="text-xs text-warm-gray font-medium block mb-1">Drafted Reply:</span>
            <p className="text-sm whitespace-pre-wrap">{result.drafted_reply}</p>
          </div>
        </Card>
      )}
    </div>
  )
}
