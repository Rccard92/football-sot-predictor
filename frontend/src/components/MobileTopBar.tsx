import { useSidebarLayout } from '../contexts/SidebarLayoutContext'
import { useCompetition } from '../contexts/CompetitionContext'

function MenuIcon() {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      className="h-5 w-5"
      aria-hidden
    >
      <line x1="4" y1="6" x2="20" y2="6" />
      <line x1="4" y1="12" x2="20" y2="12" />
      <line x1="4" y1="18" x2="20" y2="18" />
    </svg>
  )
}

export function MobileTopBar() {
  const { mobileOpen, openMobile } = useSidebarLayout()
  const { selectedCompetition } = useCompetition()

  return (
    <header className="sticky top-0 z-40 flex h-14 shrink-0 items-center gap-3 border-b border-slate-200/80 bg-slate-50/95 px-4 backdrop-blur md:hidden">
      <button
        type="button"
        id="mobile-nav-trigger"
        aria-label="Apri menu di navigazione"
        aria-expanded={mobileOpen}
        aria-controls="mobile-nav-drawer"
        onClick={openMobile}
        className="flex h-10 w-10 items-center justify-center rounded-xl border border-slate-200/80 bg-white text-slate-700 shadow-sm transition-colors hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-2"
      >
        <MenuIcon />
      </button>
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-semibold text-slate-900">SOT Predictor</p>
        <p className="truncate text-[10px] text-slate-500">
          {selectedCompetition ? `${selectedCompetition.name} ${selectedCompetition.season}` : 'Campionato…'}
        </p>
      </div>
    </header>
  )
}
