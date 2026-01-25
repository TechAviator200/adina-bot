import { useState, useEffect } from 'react'
import { getGmailStatus, connectGmail, disconnectGmail, getAppConfig } from '../api/gmail'
import type { AppConfig } from '../api/gmail'
import { useAgentLog } from '../hooks/useAgentLog'
import { useToast } from '../components/ui/Toast'
import type { GmailStatus } from '../api/types'
import Button from '../components/ui/Button'
import Card from '../components/ui/Card'

export default function SettingsPage() {
  const [status, setStatus] = useState<GmailStatus | null>(null)
  const [config, setConfig] = useState<AppConfig | null>(null)
  const [loading, setLoading] = useState(true)
  const { addLog } = useAgentLog()
  const { addToast } = useToast()

  useEffect(() => {
    Promise.all([
      getGmailStatus().then(setStatus).catch(() => {}),
      getAppConfig().then(setConfig).catch(() => {}),
    ]).finally(() => setLoading(false))
  }, [])

  async function handleConnect() {
    try {
      const result = await connectGmail()
      if (result.auth_url) {
        addLog('Opening Gmail OAuth flow...')
        addToast('Opening Gmail authorization...', 'success')
        window.open(result.auth_url, '_blank')
      } else if (result.connected) {
        addLog(`Gmail connected: ${result.email}`)
        addToast(`Gmail connected as ${result.email}`, 'success')
        setStatus(result)
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Connect failed'
      addLog(`Gmail connect error: ${msg}`)
      addToast(`Gmail connect failed: ${msg}`, 'error')
    }
  }

  async function handleDisconnect() {
    try {
      await disconnectGmail()
      addLog('Gmail disconnected')
      addToast('Gmail disconnected', 'success')
      setStatus({ connected: false, email: null, auth_url: null, message: null, error: null })
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Disconnect failed'
      addLog(`Gmail disconnect error: ${msg}`)
      addToast(`Disconnect failed: ${msg}`, 'error')
    }
  }

  return (
    <div className="max-w-md">
      <h1 className="text-xl font-semibold text-warm-cream mb-4">Settings</h1>

      <Card>
        <h2 className="font-semibold text-sm mb-3">Gmail Connection</h2>

        {loading ? (
          <p className="text-sm text-warm-gray">Checking status...</p>
        ) : status?.connected ? (
          <div className="space-y-3">
            <div className="flex items-center gap-2">
              <span className="w-2 h-2 bg-green-500 rounded-full" />
              <span className="text-sm">Connected as {status.email}</span>
            </div>
            <Button variant="secondary" size="sm" onClick={handleDisconnect}>
              Disconnect
            </Button>
          </div>
        ) : (
          <div className="space-y-3">
            <div className="flex items-center gap-2">
              <span className="w-2 h-2 bg-warm-gray rounded-full" />
              <span className="text-sm">Not connected</span>
            </div>
            {status?.error && (
              <p className="text-xs text-red-400">{status.error}</p>
            )}
            <Button size="sm" onClick={handleConnect}>
              Connect Gmail
            </Button>
          </div>
        )}

        {config?.oauth_redirect_uri && (
          <div className="mt-4 pt-3 border-t border-warm-gray/10">
            <p className="text-[11px] text-warm-gray">
              Redirect URI:{' '}
              <code className="text-warm-cream/80">{config.oauth_redirect_uri}</code>
            </p>
          </div>
        )}
      </Card>
    </div>
  )
}
