import { NAV_MAIN, NAV_TECH } from '../config/navItems'
import { useSidebarLayout } from '../contexts/SidebarLayoutContext'
import { NavLinks } from './nav/NavLinks'

function ChevronIcon({ collapsed }: { collapsed: boolean }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={`h-4 w-4 transition-transform ${collapsed ? 'rotate-180' : ''}`}
      aria-hidden
    >
      <polyline points="15 18 9 12 15 6" />
    </svg>
  )
}

export function Sidebar() {
  const { collapsed, toggleCollapsed } = useSidebarLayout()

  return (
    <aside
      className={`sticky top-0 hidden h-screen max-h-screen shrink-0 self-start flex-col border-r border-slate-200/80 bg-slate-50/80 transition-[width] duration-200 md:flex ${
        collapsed ? 'w-[72px]' : 'w-60'
      }`}
    >
      <div
        className={`border-b border-slate-200/80 ${collapsed ? 'px-2 py-4 text-center' : 'px-4 py-5'}`}
      >
        {!collapsed ? (
          <>
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Serie A</p>
            <p className="mt-1 text-base font-semibold text-slate-900">SOT Predictor</p>
            <p className="mt-0.5 text-xs text-slate-500">2025/26 · MVP</p>
          </>
        ) : (
          <p className="text-[10px] font-bold leading-tight text-slate-900" title="SOT Predictor">
            SOT
          </p>
        )}
      </div>

      <div className="flex flex-1 flex-col gap-3 overflow-y-auto p-3">
        <nav className="flex flex-col gap-0.5">
          <NavLinks items={NAV_MAIN} collapsed={collapsed} />
        </nav>

        <div className={collapsed ? 'border-t border-slate-200/80 pt-2' : 'border-t border-slate-200/80 pt-3'}>
          {!collapsed ? (
            <p className="px-3 pb-1 text-[11px] font-semibold uppercase tracking-wide text-slate-500">
              Strumenti tecnici
            </p>
          ) : null}
          <nav className="mt-0.5 flex flex-col gap-0.5">
            <NavLinks items={NAV_TECH} collapsed={collapsed} />
          </nav>
        </div>
      </div>

      <div className="border-t border-slate-200/80 p-2">
        <button
          type="button"
          onClick={toggleCollapsed}
          aria-label={collapsed ? 'Espandi menu' : 'Comprimi menu'}
          className={`flex w-full items-center rounded-xl border border-slate-200/80 bg-white text-slate-600 shadow-sm transition-colors hover:bg-slate-50 hover:text-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-2 ${
            collapsed ? 'justify-center p-2.5' : 'gap-2 px-3 py-2 text-xs font-medium'
          }`}
        >
          <ChevronIcon collapsed={collapsed} />
          {!collapsed ? <span>Comprimi menu</span> : null}
        </button>
      </div>
    </aside>
  )
}
