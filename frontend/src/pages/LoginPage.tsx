import { useState, useEffect } from 'react'
import { getGmailStatus, connectGmail, disconnectGmail } from '../api/gmail'
import { useToast } from '../components/ui/Toast'
import Button from '../components/ui/Button'
import type { GmailStatus } from '../api/types'

const ACCOUNT_EMAIL_KEY = 'adina_account_email'

export default function LoginPage() {
  const [gmailStatus, setGmailStatus] = useState<GmailStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [connecting, setConnecting] = useState(false)
  const [accountEmail, setAccountEmail] = useState(
    () => localStorage.getItem(ACCOUNT_EMAIL_KEY) ?? ''
  )
  const [emailSaved, setEmailSaved] = useState(false)
  const { addToast } = useToast()

  useEffect(() => {
    getGmailStatus()
      .then(setGmailStatus)
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  function handleSaveEmail() {
    if (!accountEmail.trim()) return
    localStorage.setItem(ACCOUNT_EMAIL_KEY, accountEmail.trim())
    setEmailSaved(true)
    setTimeout(() => setEmailSaved(false), 2000)
    addToast('Account email saved', 'success')
  }

  async function handleConnectGmail() {
    setConnecting(true)
    try {
      const result = await connectGmail()
      if (result.auth_url) {
        addToast('Opening Gmail authorization...', 'success')
        window.open(result.auth_url, '_blank')
      } else if (result.connected) {
        addToast(`Connected as ${result.email}`, 'success')
        setGmailStatus(result)
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Connection failed'
      addToast(`Gmail connect failed: ${msg}`, 'error')
    } finally {
      setConnecting(false)
    }
  }

  async function handleDisconnectGmail() {
    try {
      await disconnectGmail()
      addToast('Gmail disconnected', 'success')
      setGmailStatus({ connected: false, email: null, auth_url: null, message: null, error: null })
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Disconnect failed'
      addToast(`Disconnect failed: ${msg}`, 'error')
    }
  }

  const isConnected = gmailStatus?.connected

  return (
    <div className="max-w-md">
      <h1 className="text-xl font-semibold text-warm-cream mb-1">Log In</h1>
      <p className="text-xs text-warm-gray mb-6">
        Connect your account and email to send outreach directly from ADINA.
      </p>

      <div className="space-y-4">

        {/* Account Email */}
        <div className="bg-soft-navy border border-warm-gray/20 rounded-lg p-5 space-y-4">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-full bg-warm-gray/20 flex items-center justify-center shrink-0">
              <svg className="w-4 h-4 text-warm-gray" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                  d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
              </svg>
            </div>
            <div>
              <p className="text-sm font-medium text-warm-cream">Account</p>
              <p className="text-[11px] text-warm-gray">Your ADINA account email</p>
            </div>
          </div>

          <div className="space-y-2">
            <label className="block text-xs text-warm-gray">Email address</label>
            <div className="flex gap-2">
              <input
                type="email"
                value={accountEmail}
                onChange={(e) => { setAccountEmail(e.target.value); setEmailSaved(false) }}
                placeholder="you@example.com"
                className="flex-1 bg-warm-cream/5 border border-warm-gray/30 rounded px-3 py-2 text-sm text-warm-cream placeholder:text-warm-gray/40 outline-none focus:border-terracotta/50"
                onKeyDown={(e) => { if (e.key === 'Enter') handleSaveEmail() }}
              />
              <Button size="sm" variant="secondary" onClick={handleSaveEmail} disabled={!accountEmail.trim()}>
                {emailSaved ? 'Saved' : 'Save'}
              </Button>
            </div>
          </div>

          {accountEmail && localStorage.getItem(ACCOUNT_EMAIL_KEY) === accountEmail && (
            <div className="flex items-center gap-2">
              <span className="w-1.5 h-1.5 bg-green-500 rounded-full" />
              <span className="text-[11px] text-warm-gray">Signed in as <span className="text-warm-cream">{accountEmail}</span></span>
            </div>
          )}
        </div>

        {/* Gmail Connection */}
        <div className="bg-soft-navy border border-warm-gray/20 rounded-lg p-5 space-y-4">
          <div className="flex items-center gap-2">
            {/* Google G icon */}
            <div className="w-8 h-8 rounded-full bg-warm-cream/5 border border-warm-gray/20 flex items-center justify-center shrink-0">
              <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none">
                <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4"/>
                <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/>
                <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05"/>
                <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/>
              </svg>
            </div>
            <div>
              <p className="text-sm font-medium text-warm-cream">Gmail</p>
              <p className="text-[11px] text-warm-gray">Send outreach emails from your inbox</p>
            </div>
            {!loading && (
              <div className="ml-auto">
                <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${
                  isConnected
                    ? 'bg-green-500/20 text-green-400'
                    : 'bg-warm-gray/20 text-warm-gray'
                }`}>
                  {isConnected ? 'Connected' : 'Not connected'}
                </span>
              </div>
            )}
          </div>

          {loading ? (
            <p className="text-xs text-warm-gray">Checking connection...</p>
          ) : isConnected ? (
            <div className="space-y-3">
              <div className="flex items-center gap-2 px-3 py-2.5 bg-green-500/5 border border-green-500/20 rounded-lg">
                <span className="w-2 h-2 bg-green-500 rounded-full shrink-0" />
                <div className="min-w-0">
                  <p className="text-xs text-warm-cream font-medium truncate">{gmailStatus?.email}</p>
                  <p className="text-[10px] text-warm-gray">Emails will be sent from this address</p>
                </div>
              </div>
              <Button size="sm" variant="secondary" onClick={handleDisconnectGmail}>
                Disconnect Gmail
              </Button>
            </div>
          ) : (
            <div className="space-y-3">
              {gmailStatus?.error && (
                <p className="text-xs text-red-400/80">{gmailStatus.error}</p>
              )}
              <p className="text-xs text-warm-gray/70 leading-relaxed">
                Connect your Gmail account to send outreach emails directly from ADINA.
                Your emails will appear in your Gmail Sent folder.
              </p>
              <Button size="sm" onClick={handleConnectGmail} disabled={connecting}>
                <span className="flex items-center gap-2">
                  <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none">
                    <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4"/>
                    <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/>
                    <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05"/>
                    <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/>
                  </svg>
                  {connecting ? 'Connecting...' : 'Sign in with Gmail'}
                </span>
              </Button>
            </div>
          )}
        </div>

        {/* Info */}
        <p className="text-[11px] text-warm-gray/50 leading-relaxed px-1">
          ADINA uses Gmail OAuth to send emails on your behalf. Your credentials are never stored —
          only an access token secured on the server. You can disconnect at any time.
        </p>

      </div>
    </div>
  )
}
