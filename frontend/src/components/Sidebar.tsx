import { NavLink } from 'react-router-dom'

const nav = [
  { to: '/', label: 'Prossima giornata' },
  { to: '/dashboard', label: 'Dashboard modello' },
  { to: '/data-health', label: 'Data Health' },
  { to: '/backtest', label: 'Backtest' },
  { to: '/model-legend', label: 'Legenda Modello' },
  { to: '/admin', label: 'Admin' },
] as const

const linkClass = ({ isActive }: { isActive: boolean }) =>
  `block rounded-xl px-3 py-2 text-sm font-medium transition-colors ${
    isActive
      ? 'bg-white text-slate-900 shadow-sm'
      : 'text-slate-600 hover:bg-white/60 hover:text-slate-900'
  }`

export function Sidebar() {
  return (
    <aside className="flex w-60 shrink-0 flex-col border-r border-slate-200/80 bg-slate-50/80">
      <div className="border-b border-slate-200/80 px-4 py-5">
        <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
          Serie A
        </p>
        <p className="mt-1 text-base font-semibold text-slate-900">SOT Predictor</p>
        <p className="mt-0.5 text-xs text-slate-500">2025/26 · MVP</p>
      </div>
      <nav className="flex flex-1 flex-col gap-0.5 p-3">
        {nav.map((item) => (
          <NavLink key={item.to} to={item.to} end={item.to === '/'} className={linkClass}>
            {item.label}
          </NavLink>
        ))}
      </nav>
    </aside>
  )
}
