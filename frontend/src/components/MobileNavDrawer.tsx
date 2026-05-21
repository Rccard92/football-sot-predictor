import { useEffect, useRef } from 'react'
import { NAV_MAIN, NAV_TECH } from '../config/navItems'
import { useSidebarLayout } from '../contexts/SidebarLayoutContext'
import { NavLinks } from './nav/NavLinks'

export function MobileNavDrawer() {
  const { mobileOpen, closeMobile } = useSidebarLayout()
  const panelRef = useRef<HTMLElement>(null)

  useEffect(() => {
    if (!mobileOpen) return
    const t = window.setTimeout(() => {
      panelRef.current?.querySelector<HTMLElement>('a')?.focus()
    }, 0)
    return () => window.clearTimeout(t)
  }, [mobileOpen])

  if (!mobileOpen) return null

  return (
    <div className="fixed inset-0 z-50 md:hidden" role="presentation">
      <button
        type="button"
        aria-label="Chiudi menu"
        className="absolute inset-0 bg-slate-900/40 backdrop-blur-[1px]"
        onClick={closeMobile}
      />
      <aside
        id="mobile-nav-drawer"
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label="Menu di navigazione"
        className="absolute inset-y-0 left-0 flex w-[min(280px,85vw)] flex-col border-r border-slate-200/80 bg-slate-50 shadow-xl"
      >
        <div className="flex items-center justify-between border-b border-slate-200/80 px-4 py-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Serie A</p>
            <p className="text-base font-semibold text-slate-900">SOT Predictor</p>
          </div>
          <button
            type="button"
            aria-label="Chiudi menu di navigazione"
            onClick={closeMobile}
            className="flex h-9 w-9 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-600 hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500"
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth={2}
              className="h-4 w-4"
              aria-hidden
            >
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>

        <div className="flex flex-1 flex-col gap-3 overflow-y-auto p-3">
          <nav className="flex flex-col gap-0.5">
            <NavLinks items={NAV_MAIN} collapsed={false} onNavigate={closeMobile} />
          </nav>
          <div className="border-t border-slate-200/80 pt-3">
            <p className="px-3 pb-1 text-[11px] font-semibold uppercase tracking-wide text-slate-500">
              Strumenti tecnici
            </p>
            <nav className="mt-0.5 flex flex-col gap-0.5">
              <NavLinks items={NAV_TECH} collapsed={false} onNavigate={closeMobile} />
            </nav>
          </div>
        </div>
      </aside>
    </div>
  )
}
