import { useState, useEffect } from 'react'
import {
  getEmailAccountsStatus,
  setActiveAccount,
  disconnectAccount,
  connectSmtp,
  getGoogleConnectUrl,
  getOutlookConnectUrl,
} from '../api/emailAccounts'
import { useToast } from '../components/ui/Toast'
import type { EmailAccount, ConnectSmtpRequest } from '../api/types'
import Button from '../components/ui/Button'
import Card from '../components/ui/Card'

const PROVIDER_LABELS: Record<string, string> = {
  gmail: 'Google / Gmail',
  outlook: 'Outlook / Microsoft 365',
  yahoo: 'Yahoo Mail',
  custom_smtp: 'Custom SMTP',
}

const PROVIDER_COLORS: Record<string, string> = {
  gmail: 'bg-red-500/20 text-red-400',
  outlook: 'bg-blue-500/20 text-blue-400',
  yahoo: 'bg-purple-500/20 text-purple-400',
  custom_smtp: 'bg-warm-gray/20 text-warm-gray',
}

function ProviderBadge({ provider }: { provider: string }) {
  const cls = PROVIDER_COLORS[provider] ?? 'bg-warm-gray/20 text-warm-gray'
  return (
    <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${cls}`}>
      {PROVIDER_LABELS[provider] ?? provider}
    </span>
  )
}

interface SmtpFormState {
  provider: 'yahoo' | 'custom_smtp'
  email_address: string
  smtp_host: string
  smtp_port: string
  username: string
  password: string
}

const defaultSmtpForm: SmtpFormState = {
  provider: 'yahoo',
  email_address: '',
  smtp_host: '',
  smtp_port: '587',
  username: '',
  password: '',
}

export default function SettingsPage() {
  const [accounts, setAccounts] = useState<EmailAccount[]>([])
  const [activeAccountState, setActiveAccountState] = useState<EmailAccount | null>(null)
  const [loading, setLoading] = useState(true)
  const [showSmtpForm, setShowSmtpForm] = useState(false)
  const [smtpForm, setSmtpForm] = useState<SmtpFormState>(defaultSmtpForm)
  const [connectingSmtp, setConnectingSmtp] = useState(false)
  const [connectingGoogle, setConnectingGoogle] = useState(false)
  const [connectingOutlook, setConnectingOutlook] = useState(false)
  const { addToast } = useToast()

  async function load() {
    setLoading(true)
    try {
      const status = await getEmailAccountsStatus()
      setAccounts(status.accounts)
      setActiveAccountState(status.active_account)
    } catch {
      // silently ignore
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  async function handleSetActive(accountId: number) {
    try {
      await setActiveAccount(accountId)
      addToast('Active sending account updated', 'success')
      await load()
    } catch {
      addToast('Failed to update active account', 'error')
    }
  }

  async function handleDisconnect(accountId: number, email: string | null) {
    try {
      await disconnectAccount(accountId)
      addToast(`Disconnected ${email ?? 'account'}`, 'success')
      await load()
    } catch {
      addToast('Disconnect failed', 'error')
    }
  }

  async function handleConnectGoogle() {
    setConnectingGoogle(true)
    try {
      const result = await getGoogleConnectUrl()
      if (result.url) {
        addToast('Opening Google authorization...', 'success')
        window.open(result.url, '_blank')
        setTimeout(() => load(), 3000)
      } else {
        addToast(result.error ?? 'Google OAuth not configured', 'error')
      }
    } catch {
      addToast('Failed to start Google connection', 'error')
    } finally {
      setConnectingGoogle(false)
    }
  }

  async function handleConnectOutlook() {
    setConnectingOutlook(true)
    try {
      const result = await getOutlookConnectUrl()
      if (result.url) {
        addToast('Opening Microsoft authorization...', 'success')
        window.open(result.url, '_blank')
        setTimeout(() => load(), 3000)
      } else {
        addToast(result.error ?? 'Outlook OAuth not configured', 'error')
      }
    } catch {
      addToast('Failed to start Outlook connection', 'error')
    } finally {
      setConnectingOutlook(false)
    }
  }

  async function handleConnectSmtp(e: React.FormEvent) {
    e.preventDefault()
    setConnectingSmtp(true)
    try {
      const req: ConnectSmtpRequest = {
        provider: smtpForm.provider,
        email_address: smtpForm.email_address,
        smtp_host: smtpForm.smtp_host,
        smtp_port: Number(smtpForm.smtp_port) || 587,
        username: smtpForm.username,
        password: smtpForm.password,
      }
      const result = await connectSmtp(req)
      if (result.success) {
        addToast(`Connected ${smtpForm.email_address}`, 'success')
        setShowSmtpForm(false)
        setSmtpForm(defaultSmtpForm)
        await load()
      } else {
        addToast(result.error ?? 'Connection failed', 'error')
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Connection failed'
      addToast(msg, 'error')
    } finally {
      setConnectingSmtp(false)
    }
  }

  return (
    <div className="max-w-lg space-y-6">
      <h1 className="text-xl font-semibold text-warm-cream">Connected Sending Accounts</h1>
      <p className="text-xs text-warm-gray -mt-4">
        Emails will send from the <strong className="text-warm-cream">active</strong> connected account.
      </p>

      {/* Active account banner */}
      {activeAccountState && (
        <div className="flex items-center gap-2 px-3 py-2 bg-green-500/10 border border-green-500/20 rounded-lg">
          <span className="w-2 h-2 bg-green-500 rounded-full shrink-0" />
          <span className="text-xs text-warm-cream">
            Sending from <strong>{activeAccountState.email_address}</strong>
          </span>
          <ProviderBadge provider={activeAccountState.provider} />
        </div>
      )}

      {/* Accounts list */}
      <Card>
        <h2 className="font-semibold text-sm mb-3">Connected Accounts</h2>

        {loading ? (
          <p className="text-sm text-warm-gray">Loading...</p>
        ) : accounts.length === 0 ? (
          <p className="text-sm text-warm-gray">No accounts connected yet.</p>
        ) : (
          <div className="space-y-2">
            {accounts.map((acc) => (
              <div
                key={acc.id}
                className={`flex items-center justify-between gap-3 px-3 py-2.5 rounded-lg border ${
                  acc.is_active
                    ? 'bg-green-500/5 border-green-500/30'
                    : 'bg-warm-cream/5 border-warm-gray/10'
                }`}
              >
                <div className="flex items-center gap-2 min-w-0">
                  {acc.is_active && <span className="w-2 h-2 bg-green-500 rounded-full shrink-0" />}
                  <div className="min-w-0">
                    <p className="text-xs text-warm-cream truncate">{acc.email_address ?? '—'}</p>
                    <div className="mt-0.5">
                      <ProviderBadge provider={acc.provider} />
                      {acc.is_active && (
                        <span className="ml-1 text-[10px] text-green-400">active</span>
                      )}
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  {!acc.is_active && (
                    <Button size="sm" variant="secondary" onClick={() => handleSetActive(acc.id)}>
                      Set Active
                    </Button>
                  )}
                  <Button
                    size="sm"
                    variant="secondary"
                    onClick={() => handleDisconnect(acc.id, acc.email_address)}
                  >
                    Disconnect
                  </Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>

      {/* Connect new account */}
      <Card>
        <h2 className="font-semibold text-sm mb-3">Connect an Account</h2>
        <div className="space-y-2">
          <Button
            size="sm"
            onClick={handleConnectGoogle}
            disabled={connectingGoogle}
            className="w-full justify-center"
          >
            {connectingGoogle ? 'Opening...' : 'Connect Google / Gmail'}
          </Button>
          <Button
            size="sm"
            variant="secondary"
            onClick={handleConnectOutlook}
            disabled={connectingOutlook}
            className="w-full justify-center"
          >
            {connectingOutlook ? 'Opening...' : 'Connect Outlook / Microsoft 365'}
          </Button>
          <Button
            size="sm"
            variant="secondary"
            onClick={() => setShowSmtpForm((v) => !v)}
            className="w-full justify-center"
          >
            {showSmtpForm ? 'Cancel SMTP Setup' : 'Connect Yahoo / Custom SMTP'}
          </Button>
        </div>

        {showSmtpForm && (
          <form onSubmit={handleConnectSmtp} className="mt-4 space-y-3">
            <div className="border-t border-warm-gray/10 pt-3">
              <label className="block text-xs text-warm-gray mb-1">Provider</label>
              <select
                value={smtpForm.provider}
                onChange={(e) => setSmtpForm((f) => ({ ...f, provider: e.target.value as 'yahoo' | 'custom_smtp' }))}
                className="w-full bg-soft-navy border border-warm-gray/30 rounded px-3 py-2 text-sm text-warm-cream"
              >
                <option value="yahoo">Yahoo Mail</option>
                <option value="custom_smtp">Custom SMTP</option>
              </select>
            </div>

            <div>
              <label className="block text-xs text-warm-gray mb-1">Email Address</label>
              <input
                type="email"
                required
                value={smtpForm.email_address}
                onChange={(e) => setSmtpForm((f) => ({ ...f, email_address: e.target.value }))}
                placeholder="you@example.com"
                className="w-full bg-soft-navy border border-warm-gray/30 rounded px-3 py-2 text-sm text-warm-cream placeholder:text-warm-gray/40"
              />
            </div>

            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="block text-xs text-warm-gray mb-1">SMTP Host</label>
                <input
                  type="text"
                  required
                  value={smtpForm.smtp_host}
                  onChange={(e) => setSmtpForm((f) => ({ ...f, smtp_host: e.target.value }))}
                  placeholder={smtpForm.provider === 'yahoo' ? 'smtp.mail.yahoo.com' : 'smtp.example.com'}
                  className="w-full bg-soft-navy border border-warm-gray/30 rounded px-3 py-2 text-sm text-warm-cream placeholder:text-warm-gray/40"
                />
              </div>
              <div>
                <label className="block text-xs text-warm-gray mb-1">SMTP Port</label>
                <input
                  type="number"
                  required
                  value={smtpForm.smtp_port}
                  onChange={(e) => setSmtpForm((f) => ({ ...f, smtp_port: e.target.value }))}
                  placeholder="587"
                  className="w-full bg-soft-navy border border-warm-gray/30 rounded px-3 py-2 text-sm text-warm-cream placeholder:text-warm-gray/40"
                />
              </div>
            </div>

            <div>
              <label className="block text-xs text-warm-gray mb-1">Username</label>
              <input
                type="text"
                required
                value={smtpForm.username}
                onChange={(e) => setSmtpForm((f) => ({ ...f, username: e.target.value }))}
                placeholder="you@example.com"
                className="w-full bg-soft-navy border border-warm-gray/30 rounded px-3 py-2 text-sm text-warm-cream placeholder:text-warm-gray/40"
              />
            </div>

            <div>
              <label className="block text-xs text-warm-gray mb-1">Password / App Password</label>
              <input
                type="password"
                required
                value={smtpForm.password}
                onChange={(e) => setSmtpForm((f) => ({ ...f, password: e.target.value }))}
                placeholder="App password recommended"
                className="w-full bg-soft-navy border border-warm-gray/30 rounded px-3 py-2 text-sm text-warm-cream placeholder:text-warm-gray/40"
              />
              <p className="text-[10px] text-warm-gray/60 mt-1">
                Use an app-specific password, not your account password.
              </p>
            </div>

            <Button type="submit" size="sm" disabled={connectingSmtp} className="w-full justify-center">
              {connectingSmtp ? 'Testing connection...' : 'Connect SMTP Account'}
            </Button>
          </form>
        )}
      </Card>
    </div>
  )
}
