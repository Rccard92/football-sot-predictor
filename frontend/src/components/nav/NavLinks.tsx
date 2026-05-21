import { NavLink } from 'react-router-dom'
import type { NavItem } from '../../config/navItems'
import { NavIcon } from '../icons/NavIcons'

function linkClass(collapsed: boolean, isActive: boolean) {
  const base = collapsed
    ? 'flex items-center justify-center rounded-xl p-2.5 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-2'
    : 'flex items-center gap-2.5 rounded-xl px-3 py-2 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-2'
  return `${base} ${
    isActive
      ? 'bg-white text-slate-900 shadow-sm ring-1 ring-slate-200/80'
      : 'text-slate-600 hover:bg-white/60 hover:text-slate-900'
  }`
}

export function NavLinks({
  items,
  collapsed,
  onNavigate,
}: {
  items: NavItem[]
  collapsed: boolean
  onNavigate?: () => void
}) {
  return (
    <>
      {items.map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          end={item.to === '/'}
          title={collapsed ? item.label : undefined}
          onClick={onNavigate}
          className={({ isActive }) => linkClass(collapsed, isActive)}
        >
          <NavIcon name={item.icon} />
          {collapsed ? (
            <span className="sr-only">{item.label}</span>
          ) : (
            <span>{item.label}</span>
          )}
        </NavLink>
      ))}
    </>
  )
}
