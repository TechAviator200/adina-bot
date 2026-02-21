import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App'
import { AgentLogProvider } from './context/AgentLogContext'
import { LeadProfileProvider } from './context/LeadProfileContext'
import { ToastProvider } from './components/ui/Toast'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <AgentLogProvider>
      <LeadProfileProvider>
        <ToastProvider>
          <App />
        </ToastProvider>
      </LeadProfileProvider>
    </AgentLogProvider>
  </StrictMode>,
)
