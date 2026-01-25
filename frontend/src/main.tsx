import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App'
import { AgentLogProvider } from './context/AgentLogContext'
import { ToastProvider } from './components/ui/Toast'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <AgentLogProvider>
      <ToastProvider>
        <App />
      </ToastProvider>
    </AgentLogProvider>
  </StrictMode>,
)
