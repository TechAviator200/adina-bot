import { useState, useEffect, useCallback, useContext, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  getLeads, uploadLeads, qualifyLead, draftLead, approveLead, unapproveLead,
  workflowSend, pullLeads, updateLeadStatus, updateContactEmail,
  discoverCompaniesByIndustry, getCompanyContacts, importCompaniesAsLeads, discoverLeads,
} from '../api/leads'
import { getGmailStatus } from '../api/gmail'
import { useAgentLog } from '../hooks/useAgentLog'
import { useToast } from '../components/ui/Toast'
import { LeadProfileContext } from '../context/LeadProfileContext'
import type { Lead, DiscoveredCompany, ExecutiveContact, ImportCompanyRequest, DiscoveredLead } from '../api/types'
import Button from '../components/ui/Button'

const STATUS_TABS = ['all', 'new', 'qualified', 'drafted', 'approved', 'sent']
const demoMode = import.meta.env.VITE_DEMO_MODE === 'true'

export default function LeadsPage() {
  const { selectedLeadId, setSelectedLeadId, refreshProfile } = useContext(LeadProfileContext)
  const navigate = useNavigate()

  const [leads, setLeads] = useState<Lead[]>([])
  const [loading, setLoading] = useState(true)
  const [activeTab, setActiveTab] = useState('all')
  const [gmailConnected, setGmailConnected] = useState(false)
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set())
  const [dryRun, setDryRun] = useState(demoMode)
  const [batchRunning, setBatchRunning] = useState(false)
  const [batchResult, setBatchResult] = useState<{ action: string; succeeded: number; failed: number } | null>(null)
  const [searchOpen, setSearchOpen] = useState(false)
  const [searchDomains, setSearchDomains] = useState('')
  const [searchLoading, setSearchLoading] = useState(false)
  const [updatingStatusId, setUpdatingStatusId] = useState<number | null>(null)
  // Recipient selection modal for leads with multiple contacts
  const [sendModalLeadId, setSendModalLeadId] = useState<number | null>(null)
  const [sendRecipient, setSendRecipient] = useState('')
  const [sendingRecipient, setSendingRecipient] = useState(false)
  // Company discovery state
  const [discoverOpen, setDiscoverOpen] = useState(false)
  const [discoverIndustry, setDiscoverIndustry] = useState('')
  const [discoverCountry, setDiscoverCountry] = useState('')
  const [discoverCity, setDiscoverCity] = useState('')
  const [discoverSource, setDiscoverSource] = useState<'google' | 'google_maps'>('google_maps')
  const [discoverLimit, setDiscoverLimit] = useState(30)
  const [discoverLoading, setDiscoverLoading] = useState(false)
  const [discoveredCompanies, setDiscoveredCompanies] = useState<DiscoveredCompany[]>([])
  const [discoverMessage, setDiscoverMessage] = useState<string | null>(null)
  const [discoverCached, setDiscoverCached] = useState(false)
  const [selectedCompanies, setSelectedCompanies] = useState<Set<string>>(new Set())
  const [companyContacts, setCompanyContacts] = useState<Record<string, ExecutiveContact[]>>({})
  const [loadingContacts, setLoadingContacts] = useState<string | null>(null)
  const [importingLeads, setImportingLeads] = useState(false)
  // Tracks which contact emails the user explicitly revealed in the discover modal
  const [revealedEmails, setRevealedEmails] = useState<Set<string>>(new Set())
  // Discover modal tab + title search
  const [discoverTab, setDiscoverTab] = useState<'industry' | 'title'>('industry')
  const [discoverTitle, setDiscoverTitle] = useState('')
  const [titleResults, setTitleResults] = useState<DiscoveredLead[]>([])
  const [titleSearchLoading, setTitleSearchLoading] = useState(false)
  const [titleLimitError, setTitleLimitError] = useState<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const { addLog, startRun, logToRun, endRun } = useAgentLog()
  const { addToast } = useToast()

  useEffect(() => {
    getGmailStatus()
      .then((s) => setGmailConnected(s.connected))
      .catch(() => setGmailConnected(false))
  }, [])

  // Debounced title search — fires 1 s after the user stops typing
  useEffect(() => {
    if (!discoverTitle.trim() || discoverTab !== 'title') {
      setTitleResults([])
      setTitleLimitError(null)
      return
    }
    const timer = setTimeout(async () => {
      setTitleSearchLoading(true)
      setTitleLimitError(null)
      try {
        const result = await discoverLeads(
          discoverIndustry.trim() || discoverTitle.trim(),
          [discoverTitle.trim()],
        )
        setTitleResults(result.leads)
        if (result.message) setTitleLimitError(result.message)
      } catch (err: unknown) {
        const status = (err as { response?: { status?: number; data?: { detail?: string } } })?.response?.status
        const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
        if (status === 403) {
          setTitleLimitError(detail ?? 'Daily free search limit reached. Try again tomorrow or upgrade.')
        } else {
          setTitleLimitError(err instanceof Error ? err.message : 'Search failed')
        }
      } finally {
        setTitleSearchLoading(false)
      }
    }, 1000)
    return () => clearTimeout(timer)
  }, [discoverTitle, discoverTab, discoverIndustry])

  const fetchLeads = useCallback(async () => {
    setLoading(true)
    try {
      const data = await getLeads()
      setLeads(data)
      refreshProfile()
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Unknown error'
      addLog(`Failed to fetch leads: ${msg}`)
    } finally {
      setLoading(false)
    }
  }, [addLog, refreshProfile])

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

  // Navigate to Inbox with lead pre-selected and best contact pre-filled
  function navigateToInbox(lead: Lead) {
    const contacts = parseLeadContacts(lead)
    const emailContacts = contacts.filter((c) => c.email)
    const bestEmail = emailContacts[0]?.email ?? lead.contact_email ?? ''
    const params = new URLSearchParams({ leadId: String(lead.id) })
    if (bestEmail) params.set('email', bestEmail)
    navigate(`/inbox?${params.toString()}`)
  }

  async function handleApprove(id: number) {
    if (!gmailConnected) {
      addToast('Gmail not connected. Go to Settings to connect.', 'error')
      return
    }
    const runId = startRun(`Approve & Send lead #${id}`)
    try {
      const result = await approveLead(id)
      if (result.success) {
        endRun(runId, 'Sent')
        addToast(`Email sent for lead #${id}`, 'success')
      } else {
        endRun(runId, result.error || 'Send failed', 'error')
        addToast(result.error || 'Send failed', 'error')
      }
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

  async function handleQualify(id: number) {
    const runId = startRun(`Qualify lead #${id}`)
    try {
      await qualifyLead(id)
      endRun(runId, 'Qualified')
      addToast(`Lead #${id} marked as qualified`, 'success')
      fetchLeads()
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Qualify failed'
      endRun(runId, msg, 'error')
      addToast(`Qualify failed: ${msg}`, 'error')
    }
  }

  // Parse contacts from a lead's contacts_json field
  function parseLeadContacts(lead: Lead): Array<{ name: string; email: string | null; title: string | null }> {
    if (!lead.contacts_json) return []
    try {
      return JSON.parse(lead.contacts_json)
    } catch {
      return []
    }
  }

  // Initiate send: show recipient modal if multiple contacts, else send directly
  function initiateSend(lead: Lead) {
    if (!gmailConnected) {
      addToast('Gmail not connected. Go to Settings to connect.', 'error')
      return
    }
    const contacts = parseLeadContacts(lead)
    const emailContacts = contacts.filter((c) => c.email)
    if (emailContacts.length > 1) {
      setSendModalLeadId(lead.id)
      setSendRecipient('')
    } else {
      handleWorkflow(lead.id)
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

  async function handleSendWithRecipient() {
    if (!sendModalLeadId || !sendRecipient) return
    setSendingRecipient(true)
    try {
      // Update contact_email to the selected recipient, then send
      await updateContactEmail(sendModalLeadId, sendRecipient)
      setSendModalLeadId(null)
      setSendRecipient('')
      await handleWorkflow(sendModalLeadId)
    } catch {
      addToast('Failed to update recipient', 'error')
    } finally {
      setSendingRecipient(false)
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
      const msg = err instanceof Error ? err.message : 'Search failed'
      addToast(`Search failed: ${msg}`, 'error')
    } finally {
      setSearchLoading(false)
    }
  }

  // Company discovery functions
  async function handleDiscover() {
    if (!discoverIndustry.trim()) {
      addToast('Please enter an industry', 'error')
      return
    }
    setDiscoverLoading(true)
    setDiscoveredCompanies([])
    setDiscoverMessage(null)
    setDiscoverCached(false)
    setSelectedCompanies(new Set())
    setCompanyContacts({})
    setRevealedEmails(new Set())
    try {
      const result = await discoverCompaniesByIndustry({
        industry: discoverIndustry.trim(),
        country: discoverCountry.trim() || undefined,
        city: discoverCity.trim() || undefined,
        source: discoverSource,
        limit: discoverLimit,
      })
      setDiscoveredCompanies(result.companies)
      setDiscoverMessage(result.message)
      setDiscoverCached(result.cached)
      if (result.companies.length === 0 && !result.message) {
        addToast('No companies found for this industry', 'success')
      } else {
        addToast(`Found ${result.companies.length} companies`, 'success')
      }
    } catch (err: unknown) {
      const status = (err as { response?: { status?: number; data?: { detail?: string } } })?.response?.status
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      if (status === 403) {
        setDiscoverMessage(detail ?? 'Daily free search limit reached. Try again tomorrow or upgrade.')
      } else {
        const msg = err instanceof Error ? err.message : 'Discovery failed'
        addToast(`Discovery failed: ${msg}`, 'error')
      }
    } finally {
      setDiscoverLoading(false)
    }
  }

  async function handleGetContacts(domain: string, source: string) {
    if (!domain) {
      addToast('No domain available for this company', 'error')
      return
    }
    setLoadingContacts(domain)
    try {
      const result = await getCompanyContacts(domain, source)
      setCompanyContacts((prev) => ({ ...prev, [domain]: result.contacts }))
      if (result.contacts.length === 0) {
        addToast('No contacts found', 'success')
      } else {
        addToast(`Found ${result.contacts.length} contacts`, 'success')
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to get contacts'
      addToast(`Get contacts failed: ${msg}`, 'error')
    } finally {
      setLoadingContacts(null)
    }
  }

  function revealEmail(contactKey: string) {
    setRevealedEmails((prev) => new Set([...prev, contactKey]))
  }

  function toggleCompanySelect(key: string) {
    setSelectedCompanies((prev) => {
      const next = new Set(prev)
      next.has(key) ? next.delete(key) : next.add(key)
      return next
    })
  }

  async function handleImportSelected() {
    if (selectedCompanies.size === 0) {
      addToast('No companies selected', 'error')
      return
    }
    setImportingLeads(true)
    try {
      const toImport: ImportCompanyRequest[] = []
      for (const key of selectedCompanies) {
        const company = discoveredCompanies.find((c) => (c.domain || c.name) === key)
        if (!company) continue
        const contacts = companyContacts[company.domain || ''] || []
        // Build full contacts list (stored in contacts_json, emails not hidden on backend)
        const contactList = contacts.map((c) => ({
          name: c.name,
          title: c.title ?? null,
          email: c.email ?? null,
          linkedin_url: c.linkedin_url ?? null,
          source: c.source,
        }))
        // Primary contact: first contact with an email
        const primary = contactList.find((c) => c.email) ?? contactList[0] ?? null
        toImport.push({
          name: company.name,
          domain: company.domain,
          description: company.description,
          industry: discoverIndustry.trim() || 'Unknown',
          size: null,
          location: company.location,
          phone: company.phone,
          website_url: company.website_url,
          contact_name: primary?.name ?? null,
          contact_role: primary?.title ?? null,
          contact_email: primary?.email ?? null,
          contacts: contactList.length > 0 ? contactList : null,
          source: company.source,
        })
      }
      const result = await importCompaniesAsLeads(toImport)
      addToast(`Imported ${result.imported} leads, ${result.skipped} skipped`, 'success')
      setDiscoverOpen(false)
      setDiscoveredCompanies([])
      setSelectedCompanies(new Set())
      setCompanyContacts({})
      setRevealedEmails(new Set())
      fetchLeads()
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Import failed'
      addToast(`Import failed: ${msg}`, 'error')
    } finally {
      setImportingLeads(false)
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

  async function batchQualify() {
    await runBatch('Qualify', async (lead) => {
      try { await qualifyLead(lead.id); return null } catch { return 'failed' }
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

  // Leads in the send recipient modal
  const sendModalLead = sendModalLeadId ? leads.find((l) => l.id === sendModalLeadId) : null
  const sendModalContacts = sendModalLead
    ? parseLeadContacts(sendModalLead).filter((c) => c.email)
    : []

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
          <Button size="sm" variant="secondary" onClick={() => setDiscoverOpen(true)}>
            Discover Companies
          </Button>
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
          <Button size="sm" variant="secondary" onClick={batchQualify} disabled={batchRunning}>
            Qualify
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
          {filtered.map((lead) => {
            const isProfileSelected = selectedLeadId === lead.id
            return (
              <div
                key={lead.id}
                className={`rounded-lg p-3 border transition-colors cursor-pointer ${
                  isProfileSelected
                    ? 'bg-terracotta/10 border-terracotta/40'
                    : 'bg-soft-navy/50 border-warm-gray/10 hover:border-warm-gray/30'
                }`}
                onClick={() => setSelectedLeadId(isProfileSelected ? null : lead.id)}
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3 min-w-0">
                    <input
                      type="checkbox"
                      checked={selectedIds.has(lead.id)}
                      onChange={() => toggleSelect(lead.id)}
                      onClick={(e) => e.stopPropagation()}
                      className="accent-terracotta shrink-0"
                    />
                    <span className="text-sm font-medium truncate">{lead.company}</span>
                    <span className="text-xs text-warm-gray shrink-0">{lead.industry}</span>
                    <select
                      value={lead.status}
                      onChange={(e) => handleStatusChange(lead.id, e.target.value)}
                      disabled={updatingStatusId === lead.id}
                      onClick={(e) => e.stopPropagation()}
                      className="bg-soft-navy border border-warm-gray/30 rounded px-2 py-0.5 text-xs text-warm-cream cursor-pointer disabled:opacity-50 shrink-0"
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
                  </div>
                  <div className="flex items-center gap-1.5 shrink-0" onClick={(e) => e.stopPropagation()}>
                    {lead.status === 'new' && (
                      <Button size="sm" variant="secondary" onClick={() => handleQualify(lead.id)}>
                        Qualify
                      </Button>
                    )}
                    {lead.status === 'qualified' && (
                      <Button size="sm" variant="secondary" onClick={() => navigateToInbox(lead)}>
                        Draft
                      </Button>
                    )}
                    {lead.status === 'drafted' && (
                      <>
                        <Button size="sm" variant="secondary" onClick={() => navigateToInbox(lead)}>
                          Edit Draft
                        </Button>
                        <Button size="sm" onClick={() => handleApprove(lead.id)}>
                          Approve & Send
                        </Button>
                      </>
                    )}
                    {lead.status === 'approved' && (
                      <>
                        <Button size="sm" variant="secondary" onClick={() => handleUnapprove(lead.id)}>
                          Unapprove
                        </Button>
                        <Button
                          size="sm"
                          onClick={() => initiateSend(lead)}
                          disabled={!lead.contact_email || !gmailConnected || demoMode}
                        >
                          Send
                        </Button>
                      </>
                    )}
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      )}

      {/* Recipient Selection Modal */}
      {sendModalLeadId && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
          <div className="bg-soft-navy rounded-lg border border-warm-gray/20 p-6 w-full max-w-sm shadow-xl">
            <h2 className="text-lg font-semibold text-warm-cream mb-1">Select Recipient</h2>
            <p className="text-xs text-warm-gray mb-4">
              {sendModalLead?.company} has multiple contacts. Choose who to send to.
            </p>
            <div>
              <label className="block text-xs text-warm-gray mb-1">Recipient *</label>
              <select
                value={sendRecipient}
                onChange={(e) => setSendRecipient(e.target.value)}
                className="w-full bg-soft-navy border border-warm-gray/30 rounded px-3 py-2 text-sm text-warm-cream"
              >
                <option value="">Select a contact...</option>
                {sendModalContacts.map((c, i) => (
                  <option key={i} value={c.email!}>
                    {c.name}{c.title ? ` (${c.title})` : ''} — {c.email}
                  </option>
                ))}
              </select>
            </div>
            <div className="flex justify-end gap-2 mt-5">
              <Button
                size="sm"
                variant="secondary"
                onClick={() => { setSendModalLeadId(null); setSendRecipient('') }}
                disabled={sendingRecipient}
              >
                Cancel
              </Button>
              <Button
                size="sm"
                onClick={handleSendWithRecipient}
                disabled={!sendRecipient || sendingRecipient}
              >
                {sendingRecipient ? 'Sending...' : 'Send'}
              </Button>
            </div>
          </div>
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

      {/* Discover Companies Modal (SerpAPI) */}
      {discoverOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 overflow-y-auto p-4">
          <div className="bg-soft-navy rounded-lg border border-warm-gray/20 p-6 w-full max-w-3xl shadow-xl my-4">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-lg font-semibold text-warm-cream">Discover Companies</h2>
              <button onClick={() => setDiscoverOpen(false)} className="text-warm-gray hover:text-warm-cream">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            {/* Tab switcher */}
            <div className="flex gap-1 mb-4 border-b border-warm-gray/20 pb-2">
              {(['industry', 'title'] as const).map((tab) => (
                <button
                  key={tab}
                  onClick={() => { setDiscoverTab(tab); setTitleResults([]); setTitleLimitError(null) }}
                  className={`px-3 py-1 text-xs font-medium rounded transition-colors capitalize ${
                    discoverTab === tab
                      ? 'bg-terracotta text-warm-cream'
                      : 'text-warm-gray hover:text-warm-cream'
                  }`}
                >
                  {tab === 'industry' ? 'By Industry' : 'By Title'}
                </button>
              ))}
            </div>

            {/* ── Title Tab ── */}
            {discoverTab === 'title' && (
              <div className="mb-4 space-y-3">
                <p className="text-xs text-warm-gray">Search companies by the job title of their people. Results update 1 s after you stop typing.</p>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs text-warm-gray mb-1">Job Title *</label>
                    <input
                      type="text"
                      value={discoverTitle}
                      onChange={(e) => setDiscoverTitle(e.target.value)}
                      placeholder="e.g. CEO, COO, Founder"
                      className="w-full px-3 py-2 rounded-md bg-warm-cream/10 border border-warm-gray/20 text-warm-cream text-sm placeholder:text-warm-gray/50 focus:outline-none focus:border-terracotta"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-warm-gray mb-1">Industry (optional)</label>
                    <input
                      type="text"
                      value={discoverIndustry}
                      onChange={(e) => setDiscoverIndustry(e.target.value)}
                      placeholder="e.g. Healthcare, SaaS"
                      className="w-full px-3 py-2 rounded-md bg-warm-cream/10 border border-warm-gray/20 text-warm-cream text-sm placeholder:text-warm-gray/50 focus:outline-none focus:border-terracotta"
                    />
                  </div>
                </div>
                {titleSearchLoading && (
                  <p className="text-xs text-warm-gray flex items-center gap-1.5">
                    <svg className="animate-spin h-3 w-3" viewBox="0 0 24 24" fill="none">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
                    </svg>
                    Searching...
                  </p>
                )}
                {titleLimitError && (
                  <div className="p-3 bg-red-500/15 border border-red-500/30 rounded-lg text-xs text-red-400">
                    {titleLimitError}
                  </div>
                )}
                {titleResults.length > 0 && (
                  <div className="max-h-64 overflow-y-auto border border-warm-gray/10 rounded-lg divide-y divide-warm-gray/10">
                    {titleResults.map((lead, i) => (
                      <div key={i} className="px-3 py-2 flex items-center justify-between gap-3">
                        <div className="min-w-0">
                          <p className="text-sm text-warm-cream font-medium truncate">{lead.company}</p>
                          {lead.website && <p className="text-xs text-warm-gray/70 truncate">{lead.website}</p>}
                          {lead.description && <p className="text-xs text-warm-gray/60 line-clamp-1">{lead.description}</p>}
                        </div>
                        <div className="shrink-0 flex items-center gap-2">
                          <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${
                            lead.score >= 70 ? 'bg-green-500/20 text-green-400' :
                            lead.score >= 40 ? 'bg-yellow-500/20 text-yellow-400' :
                            'bg-warm-gray/20 text-warm-gray'
                          }`}>{Math.round(lead.score)}</span>
                          {lead.already_exists && (
                            <span className="text-[10px] text-warm-gray/50">in DB</span>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
                {!titleSearchLoading && !titleLimitError && discoverTitle.trim() && titleResults.length === 0 && (
                  <p className="text-xs text-warm-gray/60 text-center py-4">No results yet — keep typing or wait 1 s</p>
                )}
              </div>
            )}

            {/* ── By Industry Tab (existing form + results) ── */}
            {discoverTab === 'industry' && (<>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
              <div className="col-span-2">
                <label className="block text-xs text-warm-gray mb-1">Industry *</label>
                <input
                  type="text"
                  value={discoverIndustry}
                  onChange={(e) => setDiscoverIndustry(e.target.value)}
                  placeholder="e.g. Healthcare, Real Estate, SaaS"
                  className="w-full px-3 py-2 rounded-md bg-warm-cream/10 border border-warm-gray/20 text-warm-cream text-sm placeholder:text-warm-gray/50 focus:outline-none focus:border-terracotta"
                />
              </div>
              <div>
                <label className="block text-xs text-warm-gray mb-1">Country</label>
                <input
                  type="text"
                  value={discoverCountry}
                  onChange={(e) => setDiscoverCountry(e.target.value)}
                  placeholder="e.g. US, UK"
                  className="w-full px-3 py-2 rounded-md bg-warm-cream/10 border border-warm-gray/20 text-warm-cream text-sm placeholder:text-warm-gray/50 focus:outline-none focus:border-terracotta"
                />
              </div>
              <div>
                <label className="block text-xs text-warm-gray mb-1">City</label>
                <input
                  type="text"
                  value={discoverCity}
                  onChange={(e) => setDiscoverCity(e.target.value)}
                  placeholder="e.g. Austin"
                  className="w-full px-3 py-2 rounded-md bg-warm-cream/10 border border-warm-gray/20 text-warm-cream text-sm placeholder:text-warm-gray/50 focus:outline-none focus:border-terracotta"
                />
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-3 mb-4">
              <div className="flex items-center gap-2">
                <span className="text-xs text-warm-gray">Source</span>
                <div className="flex rounded-md border border-warm-gray/20 overflow-hidden">
                  <button
                    type="button"
                    onClick={() => setDiscoverSource('google_maps')}
                    className={`px-3 py-1.5 text-xs ${discoverSource === 'google_maps' ? 'bg-terracotta text-warm-cream' : 'text-warm-gray hover:text-warm-cream'}`}
                  >
                    Maps (recommended)
                  </button>
                  <button
                    type="button"
                    onClick={() => setDiscoverSource('google')}
                    className={`px-3 py-1.5 text-xs ${discoverSource === 'google' ? 'bg-terracotta text-warm-cream' : 'text-warm-gray hover:text-warm-cream'}`}
                  >
                    Web search
                  </button>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <label className="text-xs text-warm-gray">Limit</label>
                <select
                  value={discoverLimit}
                  onChange={(e) => setDiscoverLimit(Number(e.target.value))}
                  className="px-3 py-1.5 rounded-md bg-warm-cream/10 border border-warm-gray/20 text-warm-cream text-xs focus:outline-none focus:border-terracotta"
                >
                  <option value={20}>20</option>
                  <option value={30}>30</option>
                  <option value={50}>50</option>
                </select>
              </div>
            </div>

            <div className="flex items-center mb-4">
              <Button size="sm" onClick={handleDiscover} disabled={discoverLoading || !discoverIndustry.trim()}>
                {discoverLoading ? (
                  <span className="flex items-center gap-1.5">
                    <svg className="animate-spin h-3.5 w-3.5" viewBox="0 0 24 24" fill="none">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
                    </svg>
                    Searching...
                  </span>
                ) : 'Search'}
              </Button>
            </div>

            {discoverMessage && (
              <div className={`mb-4 p-3 rounded-lg text-sm ${
                discoverMessage.toLowerCase().includes('limit reached')
                  ? 'bg-red-500/15 border border-red-500/30 text-red-400'
                  : 'bg-terracotta/20 border border-terracotta/30 text-warm-cream'
              }`}>
                {discoverMessage}
              </div>
            )}

            {/* Results */}
            {discoveredCompanies.length > 0 && (
              <>
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2 text-xs text-warm-gray">
                    <span>{discoveredCompanies.length} companies found</span>
                    {discoverCached && (
                      <span className="px-2 py-0.5 rounded-full bg-warm-gray/20 text-warm-gray">Cached</span>
                    )}
                  </div>
                  {selectedCompanies.size > 0 && (
                    <Button size="sm" onClick={handleImportSelected} disabled={importingLeads}>
                      {importingLeads ? 'Importing...' : `Import ${selectedCompanies.size} Selected`}
                    </Button>
                  )}
                </div>
                <div className="max-h-80 overflow-y-auto border border-warm-gray/10 rounded-lg">
                  <div className="grid grid-cols-12 gap-2 px-3 py-2 text-xs text-warm-gray border-b border-warm-gray/10">
                    <div className="col-span-3">Company</div>
                    <div className="col-span-2">Website</div>
                    <div className="col-span-2">Phone</div>
                    <div className="col-span-2">Location</div>
                    <div className="col-span-2">Description</div>
                    <div className="col-span-1 text-right">Actions</div>
                  </div>
                  {discoveredCompanies.map((company) => {
                    const key = company.domain || company.name
                    const contacts = companyContacts[company.domain || ''] || []
                    const isSelected = selectedCompanies.has(key)
                    const canGetContacts = Boolean(company.domain)
                    return (
                      <div key={key} className="border-b border-warm-gray/10 last:border-b-0">
                        <div
                          className={`grid grid-cols-12 gap-2 px-3 py-2 text-xs ${
                            isSelected ? 'bg-terracotta/10' : ''
                          }`}
                        >
                          <div className="col-span-3 flex items-start gap-2">
                            <input
                              type="checkbox"
                              checked={isSelected}
                              onChange={() => toggleCompanySelect(key)}
                              className="accent-terracotta mt-0.5"
                            />
                            <div>
                              <div className="flex items-center gap-2">
                                <span className="text-warm-cream font-medium">{company.name}</span>
                                <span className="text-[10px] px-1.5 py-0.5 rounded bg-warm-gray/20 text-warm-gray">
                                  {company.source}
                                </span>
                              </div>
                              {company.domain && (
                                <div className="text-warm-gray/70">{company.domain}</div>
                              )}
                            </div>
                          </div>
                          <div className="col-span-2 text-warm-gray/80 truncate">
                            {company.website_url || company.domain || '—'}
                          </div>
                          <div className="col-span-2 text-warm-gray/80 truncate">
                            {company.phone || '—'}
                          </div>
                          <div className="col-span-2 text-warm-gray/80 truncate">
                            {company.location || '—'}
                          </div>
                          <div className="col-span-2 text-warm-gray/80 line-clamp-2">
                            {company.description || '—'}
                          </div>
                          <div className="col-span-1 text-right">
                            <Button
                              size="sm"
                              variant="secondary"
                              onClick={() => handleGetContacts(company.domain || '', company.source)}
                              disabled={!canGetContacts || loadingContacts === company.domain}
                            >
                              {loadingContacts === company.domain
                                ? 'Loading...'
                                : contacts.length > 0
                                ? `${contacts.length} Contacts`
                                : 'Get Contacts'}
                            </Button>
                          </div>
                        </div>
                        {/* Contacts list: emails hidden until explicitly revealed */}
                        {contacts.length > 0 && (
                          <div className="px-3 pb-2 pt-0 border-t border-warm-gray/10 space-y-1">
                            {contacts.slice(0, 5).map((contact, idx) => {
                              const emailKey = `${company.domain}-${idx}`
                              const emailRevealed = revealedEmails.has(emailKey)
                              return (
                                <div key={idx} className="flex items-center gap-2 text-xs">
                                  <span className="text-warm-cream">{contact.name}</span>
                                  {contact.title && (
                                    <span className="text-warm-gray">- {contact.title}</span>
                                  )}
                                  {contact.email && (
                                    emailRevealed ? (
                                      <span className="text-terracotta">{contact.email}</span>
                                    ) : (
                                      <button
                                        onClick={() => revealEmail(emailKey)}
                                        className="text-warm-gray/60 hover:text-terracotta text-[10px] border border-warm-gray/20 rounded px-1.5 py-0.5 transition-colors"
                                      >
                                        Reveal email
                                      </button>
                                    )
                                  )}
                                </div>
                              )
                            })}
                            {contacts.length > 5 && (
                              <p className="text-xs text-warm-gray">+{contacts.length - 5} more</p>
                            )}
                          </div>
                        )}
                      </div>
                    )
                  })}
                </div>
              </>
            )}

            {discoveredCompanies.length === 0 && !discoverLoading && (
              <div className="text-center py-8 text-warm-gray text-sm">
                Enter an industry and click Search to discover companies
              </div>
            )}
            </>)}
          </div>
        </div>
      )}
    </div>
  )
}
