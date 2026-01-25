import { NavLink } from 'react-router-dom'

const navItems = [
  { to: '/demo', label: 'Demo' },
  { to: '/leads', label: 'Leads' },
  { to: '/inbox', label: 'Inbox' },
  { to: '/sent', label: 'Sent' },
  { to: '/settings', label: 'Settings' },
]

const demoMode = import.meta.env.VITE_DEMO_MODE === 'true'

export default function Sidebar() {
  return (
    <aside className="w-52 bg-soft-navy flex flex-col border-r border-warm-gray/20">
      <div className="p-4 flex items-center gap-3">
        <img
          src="/assets/brand/adina-logo.png"
          alt="ADINA"
          className="w-10 h-10 rounded-full object-cover"
        />
        <div>
          <span className="text-warm-cream font-semibold text-sm block">ADINA Bot</span>
          {demoMode && (
            <span className="text-[10px] font-medium bg-terracotta/20 text-terracotta px-1.5 py-0.5 rounded">
              Demo Mode
            </span>
          )}
        </div>
      </div>

      <nav className="flex-1 mt-4">
        {navItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            className={({ isActive }) =>
              `block px-5 py-2.5 text-sm font-medium transition-colors ${
                isActive
                  ? 'text-terracotta border-r-2 border-terracotta bg-terracotta/10'
                  : 'text-warm-gray hover:text-warm-cream'
              }`
            }
          >
            {item.label}
          </NavLink>
        ))}
      </nav>
    </aside>
  )
}
