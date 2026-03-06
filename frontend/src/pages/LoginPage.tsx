import { useState, useEffect } from 'react'
import { getGmailStatus, disconnectGmail } from '../api/gmail'
import {
  getEmailAccountsStatus,
  disconnectAccount,
  getGoogleConnectUrl,
  getOutlookConnectUrl,
  connectSmtp,
} from '../api/emailAccounts'
import { useToast } from '../components/ui/Toast'
import Button from '../components/ui/Button'
import type { EmailAccount, ConnectSmtpRequest } from '../api/types'

// Known SMTP presets by email domain
function smtpPreset(email: string): Partial<ConnectSmtpRequest> {
  const domain = email.split('@')[1]?.toLowerCase() ?? ''
  if (domain === 'yahoo.com' || domain === 'ymail.com')
    return { provider: 'yahoo', smtp_host: 'smtp.mail.yahoo.com', smtp_port: 587 }
  if (domain === 'icloud.com')
    return { provider: 'custom_smtp', smtp_host: 'smtp.mail.me.com', smtp_port: 587 }
  return { provider: 'custom_smtp', smtp_host: '', smtp_port: 587 }
}

const GoogleIcon = () => (
  <svg className="w-4 h-4 shrink-0" viewBox="0 0 24 24" fill="none">
    <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4"/>
    <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/>
    <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05"/>
    <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/>
  </svg>
)

export default function LoginPage() {
  const [activeAccount, setActiveAccount] = useState<EmailAccount | null>(null)
  const [legacyEmail, setLegacyEmail] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [signingOut, setSigningOut] = useState(false)
  const [connectingGoogle, setConnectingGoogle] = useState(false)
  const [connectingOutlook, setConnectingOutlook] = useState(false)
  const [showSmtp, setShowSmtp] = useState(false)
  const [smtpEmail, setSmtpEmail] = useState('')
  const [smtpPassword, setSmtpPassword] = useState('')
  const [smtpHost, setSmtpHost] = useState('')
  const [smtpPort, setSmtpPort] = useState('587')
  const [connectingSmtp, setConnectingSmtp] = useState(false)
  const { addToast } = useToast()

  useEffect(() => {
    Promise.all([
      getEmailAccountsStatus().catch(() => null),
      getGmailStatus().catch(() => null),
    ]).then(([accounts, gmail]) => {
      if (accounts?.active_account) {
        setActiveAccount(accounts.active_account)
      } else if (gmail?.connected) {
        setLegacyEmail(gmail.email)
      }
    }).finally(() => setLoading(false))
  }, [])

  const isConnected = activeAccount !== null || legacyEmail !== null
  const connectedEmail = activeAccount?.email_address ?? legacyEmail
  const connectedProvider = activeAccount?.provider ?? (legacyEmail ? 'gmail' : null)

  async function handleSignOut() {
    setSigningOut(true)
    try {
      if (activeAccount) {
        await disconnectAccount(activeAccount.id)
        setActiveAccount(null)
      }
      if (legacyEmail) {
        await disconnectGmail().catch(() => {})
        setLegacyEmail(null)
      }
      addToast('Signed out successfully', 'success')
    } catch {
      addToast('Sign out failed', 'error')
    } finally {
      setSigningOut(false)
    }
  }

  async function handleConnectGoogle() {
    setConnectingGoogle(true)
    try {
      const result = await getGoogleConnectUrl()
      if (result.url) {
        window.open(result.url, '_blank')
        addToast('Complete sign-in in the popup, then return here', 'success')
      } else {
        addToast(result.error ?? 'Google sign-in not configured', 'error')
      }
    } catch {
      addToast('Failed to start Google sign-in', 'error')
    } finally {
      setConnectingGoogle(false)
    }
  }

  async function handleConnectOutlook() {
    setConnectingOutlook(true)
    try {
      const result = await getOutlookConnectUrl()
      if (result.url) {
        window.open(result.url, '_blank')
        addToast('Complete sign-in in the popup, then return here', 'success')
      } else {
        addToast(result.error ?? 'Outlook sign-in not configured', 'error')
      }
    } catch {
      addToast('Failed to start Outlook sign-in', 'error')
    } finally {
      setConnectingOutlook(false)
    }
  }

  function handleSmtpEmailChange(value: string) {
    setSmtpEmail(value)
    const preset = smtpPreset(value)
    if (preset.smtp_host) setSmtpHost(preset.smtp_host)
    if (preset.smtp_port) setSmtpPort(String(preset.smtp_port))
  }

  async function handleConnectSmtp(e: React.FormEvent) {
    e.preventDefault()
    setConnectingSmtp(true)
    try {
      const preset = smtpPreset(smtpEmail)
      const req: ConnectSmtpRequest = {
        provider: preset.provider ?? 'custom_smtp',
        email_address: smtpEmail,
        smtp_host: smtpHost,
        smtp_port: Number(smtpPort) || 587,
        username: smtpEmail,
        password: smtpPassword,
      }
      const result = await connectSmtp(req)
      if (result.success && result.account) {
        setActiveAccount(result.account)
        setShowSmtp(false)
        addToast(`Signed in as ${smtpEmail}`, 'success')
      } else {
        addToast(result.error ?? 'Connection failed — check your credentials', 'error')
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Connection failed'
      addToast(msg, 'error')
    } finally {
      setConnectingSmtp(false)
    }
  }

  return (
    <div className="max-w-sm">
      <h1 className="text-xl font-semibold text-warm-cream mb-1">Log In</h1>
      <p className="text-xs text-warm-gray mb-6">
        Connect your business email so ADINA can send outreach on your behalf.
      </p>

      {loading ? (
        <p className="text-sm text-warm-gray">Checking connection...</p>
      ) : isConnected ? (
        /* ── Signed in state ── */
        <div className="bg-soft-navy border border-warm-gray/20 rounded-lg p-5 space-y-4">
          <div className="flex items-center gap-3">
            <span className="w-2.5 h-2.5 bg-green-500 rounded-full shrink-0" />
            <div className="min-w-0">
              <p className="text-sm font-medium text-warm-cream truncate">{connectedEmail}</p>
              <p className="text-[11px] text-warm-gray capitalize">{connectedProvider} · Connected</p>
            </div>
          </div>
          <p className="text-xs text-warm-gray/70 leading-relaxed">
            Emails sent from ADINA will come from this address and appear in your Sent folder.
          </p>
          <Button
            size="sm"
            variant="secondary"
            onClick={handleSignOut}
            disabled={signingOut}
            className="w-full justify-center"
          >
            {signingOut ? 'Signing out...' : 'Sign Out'}
          </Button>
        </div>
      ) : (
        /* ── Sign in state ── */
        <div className="space-y-3">
          <Button
            size="sm"
            onClick={handleConnectGoogle}
            disabled={connectingGoogle}
            className="w-full justify-center"
          >
            <span className="flex items-center gap-2">
              <GoogleIcon />
              {connectingGoogle ? 'Opening...' : 'Sign in with Google'}
            </span>
          </Button>

          <Button
            size="sm"
            variant="secondary"
            onClick={handleConnectOutlook}
            disabled={connectingOutlook}
            className="w-full justify-center"
          >
            {connectingOutlook ? 'Opening...' : 'Sign in with Microsoft (Outlook / 365)'}
          </Button>

          <div className="relative flex items-center py-1">
            <div className="flex-1 border-t border-warm-gray/15" />
            <span className="px-3 text-[10px] text-warm-gray/50">or</span>
            <div className="flex-1 border-t border-warm-gray/15" />
          </div>

          {!showSmtp ? (
            <button
              onClick={() => setShowSmtp(true)}
              className="w-full text-xs text-warm-gray hover:text-warm-cream text-center py-1 transition-colors"
            >
              Sign in with Yahoo / other email
            </button>
          ) : (
            <form onSubmit={handleConnectSmtp} className="bg-soft-navy border border-warm-gray/20 rounded-lg p-4 space-y-3">
              <p className="text-xs font-medium text-warm-cream">Email & Password</p>

              <div>
                <label className="block text-[11px] text-warm-gray mb-1">Email address</label>
                <input
                  type="email"
                  required
                  value={smtpEmail}
                  onChange={(e) => handleSmtpEmailChange(e.target.value)}
                  placeholder="you@yourbusiness.com"
                  className="w-full bg-warm-cream/5 border border-warm-gray/30 rounded px-3 py-2 text-sm text-warm-cream placeholder:text-warm-gray/40 outline-none focus:border-terracotta/50"
                />
              </div>

              <div>
                <label className="block text-[11px] text-warm-gray mb-1">Password / App password</label>
                <input
                  type="password"
                  required
                  value={smtpPassword}
                  onChange={(e) => setSmtpPassword(e.target.value)}
                  placeholder="••••••••"
                  className="w-full bg-warm-cream/5 border border-warm-gray/30 rounded px-3 py-2 text-sm text-warm-cream placeholder:text-warm-gray/40 outline-none focus:border-terracotta/50"
                />
              </div>

              <div className="grid grid-cols-3 gap-2">
                <div className="col-span-2">
                  <label className="block text-[11px] text-warm-gray mb-1">SMTP host</label>
                  <input
                    type="text"
                    required
                    value={smtpHost}
                    onChange={(e) => setSmtpHost(e.target.value)}
                    placeholder="smtp.yourdomain.com"
                    className="w-full bg-warm-cream/5 border border-warm-gray/30 rounded px-3 py-2 text-sm text-warm-cream placeholder:text-warm-gray/40 outline-none focus:border-terracotta/50"
                  />
                </div>
                <div>
                  <label className="block text-[11px] text-warm-gray mb-1">Port</label>
                  <input
                    type="number"
                    required
                    value={smtpPort}
                    onChange={(e) => setSmtpPort(e.target.value)}
                    className="w-full bg-warm-cream/5 border border-warm-gray/30 rounded px-3 py-2 text-sm text-warm-cream outline-none focus:border-terracotta/50"
                  />
                </div>
              </div>

              <p className="text-[10px] text-warm-gray/50">
                For Yahoo, use an app password from your account security settings.
              </p>

              <div className="flex gap-2">
                <Button type="submit" size="sm" disabled={connectingSmtp} className="flex-1 justify-center">
                  {connectingSmtp ? 'Connecting...' : 'Sign In'}
                </Button>
                <Button type="button" size="sm" variant="secondary" onClick={() => setShowSmtp(false)}>
                  Cancel
                </Button>
              </div>
            </form>
          )}

          <p className="text-[11px] text-warm-gray/40 leading-relaxed text-center pt-1">
            Your credentials are encrypted and stored only on the server.
          </p>
        </div>
      )}
    </div>
  )
}
