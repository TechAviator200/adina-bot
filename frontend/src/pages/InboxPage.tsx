import { useState, useEffect } from 'react'
import { draftReply, getTemplates } from '../api/inbox'
import { getLeads } from '../api/leads'
import { useAgentLog } from '../hooks/useAgentLog'
import { useToast } from '../components/ui/Toast'
import type { Lead, ReplyDraftResponse, OutreachTemplate } from '../api/types'
import Button from '../components/ui/Button'
import Badge from '../components/ui/Badge'
import Card from '../components/ui/Card'

export default function InboxPage() {
  const [leads, setLeads] = useState<Lead[]>([])
  const [selectedLeadId, setSelectedLeadId] = useState<number | ''>('')
  const [templates, setTemplates] = useState<OutreachTemplate[]>([])
  const [selectedTemplate, setSelectedTemplate] = useState('')
  const [inboundText, setInboundText] = useState('')
  const [result, setResult] = useState<ReplyDraftResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const { addLog } = useAgentLog()
  const { addToast } = useToast()

  useEffect(() => {
    getLeads().then(setLeads).catch(() => {})
    getTemplates().then(setTemplates).catch(() => {})
  }, [])

  async function handleClassify() {
    if (!selectedLeadId || !inboundText.trim()) return
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

        <div>
          <label className="block text-xs text-warm-gray mb-1">Outreach Template</label>
          <select
            value={selectedTemplate}
            onChange={(e) => setSelectedTemplate(e.target.value)}
            className="w-full bg-soft-navy border border-warm-gray/30 rounded px-3 py-2 text-sm text-warm-cream"
          >
            <option value="">Select a template...</option>
            {templates.map((t) => (
              <option key={t.intent} value={t.intent}>
                {t.intent.charAt(0).toUpperCase() + t.intent.slice(1)} — {t.cta}
              </option>
            ))}
          </select>
          {selectedTemplate && (
            <p className="mt-1 text-xs text-warm-gray italic">
              Tone: {templates.find((t) => t.intent === selectedTemplate)?.tone}
            </p>
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

        <Button onClick={handleClassify} disabled={loading || !selectedLeadId || !inboundText.trim()}>
          {loading ? 'Classifying...' : 'Classify & Draft Reply'}
        </Button>
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
