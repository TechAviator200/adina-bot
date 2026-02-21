import { useContext, useEffect, useState } from 'react'
import { LeadProfileContext } from '../../context/LeadProfileContext'
import { getLeadProfile, fetchLeadContacts } from '../../api/leads'
import type { LeadProfile } from '../../api/types'

const STATUS_COLORS: Record<string, string> = {
  new: 'bg-warm-gray/20 text-warm-gray',
  qualified: 'bg-blue-500/20 text-blue-400',
  drafted: 'bg-yellow-500/20 text-yellow-400',
  approved: 'bg-green-500/20 text-green-400',
  sent: 'bg-terracotta/20 text-terracotta',
  ignored: 'bg-warm-gray/10 text-warm-gray/60',
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <p className="text-[10px] uppercase tracking-wide text-warm-gray mb-0.5">{label}</p>
      {children}
    </div>
  )
}

export default function ProfilePanel() {
  const { selectedLeadId, refreshKey } = useContext(LeadProfileContext)
  const [profile, setProfile] = useState<LeadProfile | null>(null)
  const [loading, setLoading] = useState(false)
  const [fetchingContacts, setFetchingContacts] = useState(false)
  const [contactsError, setContactsError] = useState<string | null>(null)

  useEffect(() => {
    if (!selectedLeadId) {
      setProfile(null)
      setContactsError(null)
      return
    }
    setLoading(true)
    getLeadProfile(selectedLeadId)
      .then(setProfile)
      .catch(() => setProfile(null))
      .finally(() => setLoading(false))
  }, [selectedLeadId, refreshKey])

  async function handleFetchContacts() {
    if (!selectedLeadId) return
    setFetchingContacts(true)
    setContactsError(null)
    try {
      const updated = await fetchLeadContacts(selectedLeadId)
      setProfile(updated)
      if (updated.contacts.length === 0) {
        setContactsError('No contacts found for this domain')
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to fetch contacts'
      setContactsError(msg)
    } finally {
      setFetchingContacts(false)
    }
  }

  return (
    <aside className="w-80 bg-soft-navy border-l border-warm-gray/20 flex flex-col shrink-0">
      <div className="p-4 border-b border-warm-gray/20">
        <h2 className="text-warm-cream font-semibold text-sm">Company Profile</h2>
      </div>

      <div className="flex-1 overflow-y-auto p-4">
        {!selectedLeadId && (
          <p className="text-warm-gray text-xs text-center mt-10">
            Click a lead to view its profile
          </p>
        )}

        {selectedLeadId && loading && (
          <p className="text-warm-gray text-xs text-center mt-10">Loading...</p>
        )}

        {profile && !loading && (
          <div className="space-y-4">
            {/* Header */}
            <div>
              <h3 className="text-warm-cream font-semibold text-base leading-tight">{profile.company}</h3>
              <div className="flex items-center gap-2 mt-1 flex-wrap">
                <span className={`text-[10px] px-2 py-0.5 rounded-full capitalize font-medium ${STATUS_COLORS[profile.status] ?? 'bg-warm-gray/20 text-warm-gray'}`}>
                  {profile.status}
                </span>
                {profile.industry && (
                  <span className="text-xs text-warm-gray">{profile.industry}</span>
                )}
              </div>
            </div>

            <div className="border-t border-warm-gray/10" />

            {/* Website */}
            {profile.website && (
              <Field label="Website">
                <a
                  href={profile.website.startsWith('http') ? profile.website : `https://${profile.website}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-xs text-terracotta hover:underline break-all"
                >
                  {profile.website}
                </a>
              </Field>
            )}

            {/* Phone */}
            {profile.phone && (
              <Field label="Phone">
                <a href={`tel:${profile.phone}`} className="text-xs text-warm-cream hover:text-terracotta">
                  {profile.phone}
                </a>
              </Field>
            )}

            {/* Location */}
            {profile.location && (
              <Field label="Location">
                <p className="text-xs text-warm-cream">{profile.location}</p>
              </Field>
            )}

            {/* Employees + Stage on same row */}
            {(profile.employees || profile.stage) && (
              <div className="flex gap-4">
                {profile.employees && (
                  <Field label="Employees">
                    <p className="text-xs text-warm-cream">{profile.employees.toLocaleString()}</p>
                  </Field>
                )}
                {profile.stage && (
                  <Field label="Stage">
                    <p className="text-xs text-warm-cream">{profile.stage}</p>
                  </Field>
                )}
              </div>
            )}

            {/* Company LinkedIn */}
            {profile.linkedin_url && (
              <Field label="LinkedIn">
                <a
                  href={profile.linkedin_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-xs text-terracotta hover:underline break-all"
                >
                  {profile.linkedin_url}
                </a>
              </Field>
            )}

            {/* Description */}
            {profile.description && (
              <Field label="About">
                <p className="text-xs text-warm-cream/80 leading-relaxed">{profile.description}</p>
              </Field>
            )}

            {(profile.website || profile.phone || profile.location || profile.employees || profile.stage || profile.linkedin_url || profile.description) && (
              <div className="border-t border-warm-gray/10" />
            )}

            {/* Contacts */}
            {profile.contacts.length > 0 ? (
              <div>
                <div className="flex items-center justify-between mb-2">
                  <p className="text-[10px] uppercase tracking-wide text-warm-gray">
                    Contacts ({profile.contacts.length})
                  </p>
                  {profile.website && (
                    <button
                      onClick={handleFetchContacts}
                      disabled={fetchingContacts}
                      className="text-[10px] text-warm-gray hover:text-terracotta disabled:opacity-50 transition-colors"
                    >
                      {fetchingContacts ? 'Refreshing...' : '↺ Refresh'}
                    </button>
                  )}
                </div>
                <div className="space-y-2">
                  {profile.contacts.map((c, i) => (
                    <div
                      key={i}
                      className="bg-warm-cream/5 border border-warm-gray/10 rounded-lg p-3 space-y-1"
                    >
                      <p className="text-xs text-warm-cream font-medium">{c.name}</p>
                      {c.title && (
                        <p className="text-[11px] text-warm-gray">{c.title}</p>
                      )}
                      {c.email && (
                        <a
                          href={`mailto:${c.email}`}
                          className="text-[11px] text-terracotta hover:underline block"
                        >
                          {c.email}
                        </a>
                      )}
                      {c.linkedin_url && (
                        <a
                          href={c.linkedin_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-[11px] text-warm-gray hover:text-warm-cream flex items-center gap-1"
                        >
                          <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 24 24">
                            <path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433a2.062 2.062 0 01-2.063-2.065 2.064 2.064 0 112.063 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z"/>
                          </svg>
                          LinkedIn
                        </a>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            ) : profile.contact_email ? (
              /* Single contact fallback */
              <div>
                <p className="text-[10px] uppercase tracking-wide text-warm-gray mb-2">Point of Contact</p>
                <div className="bg-warm-cream/5 border border-warm-gray/10 rounded-lg p-3 space-y-1">
                  {profile.contact_name && (
                    <p className="text-xs text-warm-cream font-medium">{profile.contact_name}</p>
                  )}
                  <a
                    href={`mailto:${profile.contact_email}`}
                    className="text-[11px] text-terracotta hover:underline block"
                  >
                    {profile.contact_email}
                  </a>
                </div>
              </div>
            ) : (
              <div className="text-center py-3 space-y-2">
                <p className="text-xs text-warm-gray/60">No contacts stored</p>
                {profile.website ? (
                  <>
                    <button
                      onClick={handleFetchContacts}
                      disabled={fetchingContacts}
                      className="text-xs text-terracotta hover:underline disabled:opacity-50 transition-colors"
                    >
                      {fetchingContacts ? 'Looking up contacts...' : 'Find Contacts via Hunter.io'}
                    </button>
                    {contactsError && (
                      <p className="text-[11px] text-warm-gray">{contactsError}</p>
                    )}
                  </>
                ) : (
                  <p className="text-[11px] text-warm-gray">Add a website to enable contact lookup</p>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </aside>
  )
}
