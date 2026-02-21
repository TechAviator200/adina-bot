import { useLocation, Outlet } from 'react-router-dom'
import Sidebar from './Sidebar'
import AgentPanel from './AgentPanel'
import ProfilePanel from './ProfilePanel'

export default function AppLayout() {
  const location = useLocation()
  const isLeadsPage = location.pathname === '/leads'

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar />
      <main className="flex-1 overflow-y-auto p-6 min-w-0">
        <Outlet />
      </main>
      {isLeadsPage ? <ProfilePanel /> : <AgentPanel />}
    </div>
  )
}
