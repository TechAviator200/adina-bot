import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import AppLayout from './components/layout/AppLayout'
import LeadsPage from './pages/LeadsPage'
import InboxPage from './pages/InboxPage'
import SentPage from './pages/SentPage'
import SettingsPage from './pages/SettingsPage'
import DemoPage from './pages/DemoPage'
import LoginPage from './pages/LoginPage'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AppLayout />}>
          <Route path="/" element={<Navigate to="/leads" replace />} />
          <Route path="/leads" element={<LeadsPage />} />
          <Route path="/inbox" element={<InboxPage />} />
          <Route path="/sent" element={<SentPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/demo" element={<DemoPage />} />
          <Route path="/login" element={<LoginPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
