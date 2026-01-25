import { useState, useEffect } from 'react'
import { getSentEmails } from '../api/inbox'
import type { SentEmail } from '../api/types'

export default function SentPage() {
  const [emails, setEmails] = useState<SentEmail[]>([])
  const [loading, setLoading] = useState(true)
  const [expandedId, setExpandedId] = useState<number | null>(null)

  useEffect(() => {
    getSentEmails()
      .then(setEmails)
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  return (
    <div>
      <h1 className="text-xl font-semibold text-warm-cream mb-4">Sent Emails</h1>

      {loading ? (
        <p className="text-warm-gray text-sm">Loading...</p>
      ) : emails.length === 0 ? (
        <p className="text-warm-gray text-sm">No sent emails yet</p>
      ) : (
        <div className="space-y-2">
          {emails.map((email) => (
            <div
              key={email.id}
              className="bg-soft-navy/50 rounded-lg p-3 border border-warm-gray/10"
            >
              <div
                className="flex items-center justify-between cursor-pointer"
                onClick={() => setExpandedId(expandedId === email.id ? null : email.id)}
              >
                <div className="flex items-center gap-3">
                  <span className="text-sm font-medium">{email.subject}</span>
                  <span className="text-xs text-warm-gray">{email.to_email}</span>
                </div>
                <span className="text-xs text-warm-gray">
                  {new Date(email.sent_at).toLocaleDateString()}
                </span>
              </div>

              {expandedId === email.id && (
                <div className="mt-3 pt-3 border-t border-warm-gray/10">
                  <p className="text-xs text-warm-gray mb-1">Lead #{email.lead_id}</p>
                  <p className="text-sm whitespace-pre-wrap">{email.body}</p>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
