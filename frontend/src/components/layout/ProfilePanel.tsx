import { useContext, useEffect, useState } from 'react'
import { LeadProfileContext } from '../../context/LeadProfileContext'
import { getLeadProfile } from '../../api/leads'
import type { LeadProfile } from '../../api/types'

const STATUS_COLORS: Record<string, string> = {
  new: 'text-warm-gray',
  qualified: 'text-blue-400',
  drafted: 'text-yellow-400',
  approved: 'text-green-400',
  sent: 'text-terracotta',
}

export default function ProfilePanel() {
  const { selectedLeadId } = useContext(LeadProfileContext)
  const [profile, setProfile] = useState<LeadProfile | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!selectedLeadId) {
      setProfile(null)
      return
    }
    setLoading(true)
    getLeadProfile(selectedLeadId)
      .then(setProfile)
      .catch(() => setProfile(null))
      .finally(() => setLoading(false))
  }, [selectedLeadId])

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
              <h3 className="text-warm-cream font-semibold text-sm">{profile.company}</h3>
              <div className="flex items-center gap-2 mt-0.5">
                <span className={`text-xs capitalize ${STATUS_COLORS[profile.status] ?? 'text-warm-gray'}`}>
                  {profile.status}
                </span>
                {profile.industry && (
                  <span className="text-xs text-warm-gray">· {profile.industry}</span>
                )}
              </div>
            </div>

            {/* Website */}
            {profile.website && (
              <div>
                <p className="text-[10px] uppercase tracking-wide text-warm-gray mb-0.5">Website</p>
                <a
                  href={profile.website.startsWith('http') ? profile.website : `https://${profile.website}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-xs text-terracotta hover:underline break-all"
                >
                  {profile.website}
                </a>
              </div>
            )}

            {/* Phone */}
            {profile.phone && (
              <div>
                <p className="text-[10px] uppercase tracking-wide text-warm-gray mb-0.5">Phone</p>
                <p className="text-xs text-warm-cream">{profile.phone}</p>
              </div>
            )}

            {/* Location */}
            {profile.location && (
              <div>
                <p className="text-[10px] uppercase tracking-wide text-warm-gray mb-0.5">Location</p>
                <p className="text-xs text-warm-cream">{profile.location}</p>
              </div>
            )}

            {/* Description */}
            {profile.description && (
              <div>
                <p className="text-[10px] uppercase tracking-wide text-warm-gray mb-0.5">About</p>
                <p className="text-xs text-warm-cream/80 leading-relaxed">{profile.description}</p>
              </div>
            )}

            {/* Contacts */}
            {profile.contacts.length > 0 && (
              <div>
                <p className="text-[10px] uppercase tracking-wide text-warm-gray mb-1">
                  Contacts ({profile.contacts.length})
                </p>
                <div className="space-y-2">
                  {profile.contacts.map((c, i) => (
                    <div
                      key={i}
                      className="bg-warm-cream/5 border border-warm-gray/10 rounded p-2 space-y-0.5"
                    >
                      <p className="text-xs text-warm-cream font-medium">{c.name}</p>
                      {c.title && (
                        <p className="text-xs text-warm-gray">{c.title}</p>
                      )}
                      {c.email && (
                        <p className="text-xs text-terracotta">{c.email}</p>
                      )}
                      {c.linkedin_url && (
                        <a
                          href={c.linkedin_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-xs text-warm-gray hover:text-warm-cream"
                        >
                          LinkedIn ↗
                        </a>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* No contacts fallback */}
            {profile.contacts.length === 0 && !profile.contact_email && (
              <div className="mt-4 text-xs text-warm-gray text-center">
                No contacts stored
              </div>
            )}
          </div>
        )}
      </div>
    </aside>
  )
}
