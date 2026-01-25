import { useState, useEffect, useCallback, useRef } from 'react'
import { getLeads, uploadLeads, scoreLead, draftLead, approveLead, unapproveLead, workflowSend, pullLeads, updateLeadStatus } from '../api/leads'
import { getGmailStatus } from '../api/gmail'
import { useAgentLog } from '../hooks/useAgentLog'
import { useToast } from '../components/ui/Toast'
import type { Lead } from '../api/types'
import Button from '../components/ui/Button'

const STATUS_TABS = ['all', 'new', 'qualified', 'drafted', 'approved', 'sent']
const demoMode = import.meta.env.VITE_DEMO_MODE === 'true'

export default function LeadsPage() {
  const [leads, setLeads] = useState<Lead[]>([])
  const [loading, setLoading] = useState(true)
  const [activeTab, setActiveTab] = useState('all')
  const [expandedId, setExpandedId] = useState<number | null>(null)
  const [reasonId, setReasonId] = useState<number | null>(null)
  const [gmailConnected, setGmailConnected] = useState(false)
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set())
  const [dryRun, setDryRun] = useState(demoMode)
  const [batchRunning, setBatchRunning] = useState(false)
  const [batchResult, setBatchResult] = useState<{ action: string; succeeded: number; failed: number } | null>(null)
  const [searchOpen, setSearchOpen] = useState(false)
  const [searchDomains, setSearchDomains] = useState('')
  const [searchLoading, setSearchLoading] = useState(false)
  const [updatingStatusId, setUpdatingStatusId] = useState<number | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const { addLog, startRun, logToRun, endRun } = useAgentLog()
  const { addToast } = useToast()

  useEffect(() => {
    getGmailStatus()
      .then((s) => setGmailConnected(s.connected))
      .catch(() => setGmailConnected(false))
  }, [])

  const fetchLeads = useCallback(async () => {
    setLoading(true)
    try {
      const data = await getLeads()
      setLeads(data)
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Unknown error'
      addLog(`Failed to fetch leads: ${msg}`)
    } finally {
      setLoading(false)
    }
  }, [addLog])

  useEffect(() => { fetchLeads() }, [fetchLeads])

  const filtered = activeTab === 'all' ? leads : leads.filter((l) => l.status === activeTab)

  async function handleUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    const runId = startRun(`Upload: ${file.name}`)
    try {
      const result = await uploadLeads(file)
      endRun(runId, `${result.inserted} inserted, ${result.skipped} skipped`)
      addToast(`Uploaded: ${result.inserted} inserted, ${result.skipped} skipped`, 'success')
      fetchLeads()
    } catch (err: unknown) {
      console.error('[Upload] Error:', err)
      const msg = err instanceof Error ? err.message : 'Upload failed'
      endRun(runId, msg, 'error')
      addToast(`Upload failed: ${msg}`, 'error')
    }
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  async function handleScore(id: number) {
    const runId = startRun(`Score lead #${id}`)
    try {
      const result = await scoreLead(id)
      endRun(runId, `${result.score}pts — ${result.reasons[0] || 'Scored'}`)
      addToast(`Lead #${id} scored: ${result.score}pts`, 'success')
      fetchLeads()
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Score failed'
      endRun(runId, msg, 'error')
      addToast(`Score failed: ${msg}`, 'error')
    }
  }

  async function handleDraft(id: number) {
    const runId = startRun(`Draft lead #${id}`)
    try {
      const result = await draftLead(id)
      endRun(runId, `"${result.subject}"`)
      addToast(`Draft created for lead #${id}`, 'success')
      fetchLeads()
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Draft failed'
      endRun(runId, msg, 'error')
      addToast(`Draft failed: ${msg}`, 'error')
    }
  }

  async function handleApprove(id: number) {
    const runId = startRun(`Approve lead #${id}`)
    try {
      await approveLead(id)
      endRun(runId, 'Approved')
      addToast(`Lead #${id} approved`, 'success')
      fetchLeads()
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Approve failed'
      endRun(runId, msg, 'error')
      addToast(`Approve failed: ${msg}`, 'error')
    }
  }

  async function handleUnapprove(id: number) {
    const runId = startRun(`Unapprove lead #${id}`)
    try {
      await unapproveLead(id)
      endRun(runId, 'Unapproved')
      addToast(`Lead #${id} unapproved`, 'success')
      fetchLeads()
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Unapprove failed'
      endRun(runId, msg, 'error')
      addToast(`Unapprove failed: ${msg}`, 'error')
    }
  }

  async function handleWorkflow(id: number) {
    const runId = startRun(`Send lead #${id}`)
    try {
      const result = await workflowSend(id, false)
      if (result.status === 'sent') {
        endRun(runId, 'Sent successfully')
        addToast(`Email sent for lead #${id}`, 'success')
      } else {
        endRun(runId, result.error || result.status, 'error')
        addToast(`Send issue: ${result.error || result.status}`, 'error')
      }
      fetchLeads()
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Workflow failed'
      endRun(runId, msg, 'error')
      addToast(`Send failed: ${msg}`, 'error')
    }
  }

  function toggleSelect(id: number) {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }

  function toggleSelectAll() {
    if (selectedIds.size === filtered.length) {
      setSelectedIds(new Set())
    } else {
      setSelectedIds(new Set(filtered.map((l) => l.id)))
    }
  }

  async function runBatch(
    action: string,
    fn: (lead: Lead) => Promise<string | null>,
    eligibleStatus?: string
  ) {
    const targets = filtered.filter(
      (l) => selectedIds.has(l.id) && (!eligibleStatus || l.status === eligibleStatus)
    )
    if (targets.length === 0) {
      addToast(`No eligible leads selected for ${action}`, 'error')
      return
    }
    const runId = startRun(`Batch ${action}: ${targets.length} leads`)
    setBatchRunning(true)
    setBatchResult(null)
    let succeeded = 0
    let failed = 0
    for (const lead of targets) {
      const err = await fn(lead)
      if (!err) {
        succeeded++
        logToRun(runId, `#${lead.id} ${lead.company} — done`)
      } else {
        failed++
        logToRun(runId, `#${lead.id} ${lead.company} — ${err}`)
      }
    }
    const summary = `${succeeded} succeeded, ${failed} failed`
    endRun(runId, summary, failed > 0 ? 'error' : 'done')
    setBatchRunning(false)
    setBatchResult({ action, succeeded, failed })
    setSelectedIds(new Set())
    fetchLeads()
    addToast(`Batch ${action}: ${summary}`, failed === 0 ? 'success' : 'error')
  }

  async function handleSearch() {
    const domains = searchDomains.split(',').map((d) => d.trim()).filter(Boolean)
    console.log('Search triggered with:', domains)
    if (domains.length === 0) {
      addToast('Please provide at least one domain', 'error')
      return
    }
    setSearchLoading(true)
    try {
      const result = await pullLeads(domains)
      addToast(`${result.new_leads_added} new leads added`, 'success')
      setSearchOpen(false)
      setSearchDomains('')
      fetchLeads()
    } catch (err: unknown) {
      console.error('[Search] Error:', err)
      const msg = err instanceof Error ? err.message : 'Search failed'
      addToast(`Search failed: ${msg}`, 'error')
    } finally {
      setSearchLoading(false)
    }
  }

  async function handleStatusChange(leadId: number, newStatus: string) {
    setUpdatingStatusId(leadId)
    try {
      await updateLeadStatus(leadId, newStatus)
      addToast(`Lead #${leadId} status → ${newStatus}`, 'success')
      setLeads((prev) =>
        prev.map((l) => (l.id === leadId ? { ...l, status: newStatus } : l))
      )
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Status update failed'
      addToast(`Status update failed: ${msg}`, 'error')
    } finally {
      setUpdatingStatusId(null)
    }
  }

  async function batchScore() {
    await runBatch('Score', async (lead) => {
      try { await scoreLead(lead.id); return null } catch { return 'failed' }
    }, 'new')
  }

  async function batchDraft() {
    await runBatch('Draft', async (lead) => {
      try { await draftLead(lead.id); return null } catch { return 'failed' }
    }, 'qualified')
  }

  async function batchApprove() {
    await runBatch('Approve', async (lead) => {
      try { await approveLead(lead.id); return null } catch { return 'failed' }
    }, 'drafted')
  }

  async function batchSend() {
    await runBatch('Send', async (lead) => {
      try {
        const r = await workflowSend(lead.id, dryRun)
        if (r.status === 'sent' || (dryRun && r.status !== 'error')) return null
        return r.error || r.status
      } catch { return 'failed' }
    }, 'approved')
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-xl font-semibold text-warm-cream">Leads</h1>
        <div className="flex gap-2">
          <input
            ref={fileInputRef}
            type="file"
            accept=".csv"
            onChange={handleUpload}
            className="hidden"
          />
          <Button size="sm" variant="secondary" onClick={() => setSearchOpen(true)}>
            Pull by Domain
          </Button>
          <Button size="sm" onClick={() => fileInputRef.current?.click()}>
            Upload CSV
          </Button>
        </div>
      </div>

      {/* Status tabs */}
      <div className="flex gap-1 mb-4 border-b border-warm-gray/20 pb-2">
        {STATUS_TABS.map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`px-3 py-1 text-xs font-medium rounded transition-colors ${
              activeTab === tab
                ? 'bg-terracotta text-warm-cream'
                : 'text-warm-gray hover:text-warm-cream'
            }`}
          >
            {tab}
          </button>
        ))}
      </div>

      {/* Batch action bar */}
      {selectedIds.size > 0 && (
        <div className="flex items-center gap-2 mb-3 p-2 bg-soft-navy/70 rounded-lg border border-warm-gray/20">
          <span className="text-xs text-warm-gray mr-1">{selectedIds.size} selected</span>
          <Button size="sm" variant="secondary" onClick={batchScore} disabled={batchRunning}>
            Score
          </Button>
          <Button size="sm" variant="secondary" onClick={batchDraft} disabled={batchRunning}>
            Draft
          </Button>
          <Button size="sm" variant="secondary" onClick={batchApprove} disabled={batchRunning}>
            Approve
          </Button>
          <Button size="sm" onClick={batchSend} disabled={batchRunning || (demoMode && !dryRun)}>
            {dryRun ? 'Send (dry)' : 'Send'}
          </Button>
          <label className="flex items-center gap-1 text-xs text-warm-gray ml-auto cursor-pointer">
            <input
              type="checkbox"
              checked={dryRun}
              onChange={() => { if (!demoMode) setDryRun(!dryRun) }}
              disabled={demoMode}
              className="accent-terracotta"
            />
            Dry run {demoMode && '(required)'}
          </label>
          <button
            onClick={() => setSelectedIds(new Set())}
            className="text-xs text-warm-gray hover:text-warm-cream ml-2"
          >
            Clear
          </button>
        </div>
      )}

      {/* Batch result summary */}
      {batchResult && (
        <div className="flex items-center gap-2 mb-3 p-2 bg-soft-navy/50 rounded-lg border border-warm-gray/10 text-xs">
          <span className="text-warm-cream font-medium">{batchResult.action} complete:</span>
          <span className="text-green-400">{batchResult.succeeded} succeeded</span>
          {batchResult.failed > 0 && <span className="text-terracotta">{batchResult.failed} failed</span>}
          <button
            onClick={() => setBatchResult(null)}
            className="text-warm-gray hover:text-warm-cream ml-auto"
          >
            Dismiss
          </button>
        </div>
      )}

      {loading ? (
        <p className="text-warm-gray text-sm">Loading...</p>
      ) : filtered.length === 0 ? (
        <p className="text-warm-gray text-sm">No leads found</p>
      ) : (
        <div className="space-y-2">
          {/* Select all */}
          <label className="flex items-center gap-2 px-3 py-1 text-xs text-warm-gray cursor-pointer">
            <input
              type="checkbox"
              checked={selectedIds.size === filtered.length && filtered.length > 0}
              onChange={toggleSelectAll}
              className="accent-terracotta"
            />
            Select all
          </label>
          {filtered.map((lead) => (
            <div
              key={lead.id}
              className="bg-soft-navy/50 rounded-lg p-3 border border-warm-gray/10"
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <input
                    type="checkbox"
                    checked={selectedIds.has(lead.id)}
                    onChange={() => toggleSelect(lead.id)}
                    className="accent-terracotta"
                  />
                  <span className="text-sm font-medium">{lead.company}</span>
                  <span className="text-xs text-warm-gray">{lead.industry}</span>
                  <select
                    value={lead.status}
                    onChange={(e) => handleStatusChange(lead.id, e.target.value)}
                    disabled={updatingStatusId === lead.id}
                    className="bg-soft-navy border border-warm-gray/30 rounded px-2 py-0.5 text-xs text-warm-cream cursor-pointer disabled:opacity-50"
                  >
                    <option value="new">New</option>
                    <option value="in_progress">In Progress</option>
                    <option value="contacted">Contacted</option>
                    <option value="qualified">Qualified</option>
                    <option value="drafted">Drafted</option>
                    <option value="approved">Approved</option>
                    <option value="sent">Sent</option>
                    <option value="ignored">Ignored</option>
                  </select>
                  {lead.score > 0 && (
                    <button
                      onClick={() => setReasonId(reasonId === lead.id ? null : lead.id)}
                      className="text-xs text-terracotta font-medium hover:underline"
                    >
                      {lead.score}pts {reasonId === lead.id ? '▾' : '▸'}
                    </button>
                  )}
                </div>
                <div className="flex items-center gap-1.5">
                  {lead.status === 'new' && (
                    <Button size="sm" variant="secondary" onClick={() => handleScore(lead.id)}>
                      Score
                    </Button>
                  )}
                  {lead.status === 'qualified' && (
                    <Button size="sm" variant="secondary" onClick={() => handleDraft(lead.id)}>
                      Draft
                    </Button>
                  )}
                  {lead.status === 'drafted' && (
                    <Button size="sm" onClick={() => handleApprove(lead.id)}>
                      Approve
                    </Button>
                  )}
                  {lead.status === 'approved' && (
                    <>
                      <Button size="sm" variant="secondary" onClick={() => handleUnapprove(lead.id)}>
                        Unapprove
                      </Button>
                      <Button
                        size="sm"
                        onClick={() => handleWorkflow(lead.id)}
                        disabled={!lead.contact_email || !gmailConnected || demoMode}
                      >
                        Send
                      </Button>
                    </>
                  )}
                  <button
                    onClick={() => setExpandedId(expandedId === lead.id ? null : lead.id)}
                    className="text-warm-gray hover:text-warm-cream text-xs ml-2"
                  >
                    {expandedId === lead.id ? 'Hide' : 'Details'}
                  </button>
                </div>
              </div>

              {lead.status === 'approved' && (!lead.contact_email || !gmailConnected || demoMode) && (
                <p className="text-xs text-warm-gray mt-1 text-right">
                  {!lead.contact_email ? 'No contact email' : demoMode ? 'Demo mode — use dry run' : 'Gmail not connected'}
                </p>
              )}

              {reasonId === lead.id && lead.score > 0 && (
                <div className="mt-2 pt-2 border-t border-warm-gray/10 text-xs space-y-1.5">
                  <p className="font-medium text-terracotta">Why ADINA chose this lead</p>
                  <p className="text-warm-gray">Score: <span className="text-warm-cream font-medium">{lead.score}pts</span></p>
                  {lead.score_reason && (
                    <ul className="list-disc list-inside space-y-0.5 text-warm-gray">
                      {lead.score_reason.split('\n').filter(Boolean).map((r, i) => (
                        <li key={i}>{r}</li>
                      ))}
                    </ul>
                  )}
                  {(lead.source_url || lead.website) && (
                    <p>
                      <a
                        href={lead.source_url || lead.website || '#'}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-terracotta hover:underline"
                      >
                        {lead.source_url?.includes('linkedin') ? 'LinkedIn Profile' : 'Website'} ↗
                      </a>
                    </p>
                  )}
                </div>
              )}

              {expandedId === lead.id && (
                <div className="mt-3 pt-3 border-t border-warm-gray/10 text-xs space-y-1">
                  {lead.contact_email && <p><span className="text-warm-gray">Email:</span> {lead.contact_email}</p>}
                  {lead.location && <p><span className="text-warm-gray">Location:</span> {lead.location}</p>}
                  {lead.employees && <p><span className="text-warm-gray">Employees:</span> {lead.employees}</p>}
                  {lead.stage && <p><span className="text-warm-gray">Stage:</span> {lead.stage}</p>}
                  {lead.email_subject && (
                    <div className="mt-2 bg-warm-cream/10 rounded p-2">
                      <p className="font-medium">{lead.email_subject}</p>
                      <p className="text-warm-gray mt-1 whitespace-pre-wrap">{lead.email_body}</p>
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Pull Leads by Domain Modal (Hunter.io) */}
      {searchOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
          <div className="bg-soft-navy rounded-lg border border-warm-gray/20 p-6 w-full max-w-md shadow-xl">
            <h2 className="text-lg font-semibold text-warm-cream mb-2">Pull Leads by Domain</h2>
            <p className="text-xs text-warm-gray mb-4">Enter company domains to find contacts via Hunter.io</p>
            <div className="space-y-3">
              <div>
                <label className="block text-xs text-warm-gray mb-1">Company Domains (comma separated)</label>
                <input
                  type="text"
                  value={searchDomains}
                  onChange={(e) => setSearchDomains(e.target.value)}
                  placeholder="e.g. hubspot.com, stripe.com, notion.so"
                  className="w-full px-3 py-2 rounded-md bg-warm-cream/10 border border-warm-gray/20 text-warm-cream text-sm placeholder:text-warm-gray/50 focus:outline-none focus:border-terracotta"
                />
              </div>
            </div>
            <div className="flex justify-end gap-2 mt-5">
              <Button size="sm" variant="secondary" onClick={() => setSearchOpen(false)} disabled={searchLoading}>
                Cancel
              </Button>
              <Button size="sm" onClick={handleSearch} disabled={searchLoading}>
                {searchLoading ? (
                  <span className="flex items-center gap-1.5">
                    <svg className="animate-spin h-3.5 w-3.5" viewBox="0 0 24 24" fill="none">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
                    </svg>
                    Pulling...
                  </span>
                ) : 'Pull Leads'}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
