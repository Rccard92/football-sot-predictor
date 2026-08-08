import type { BetBuilderPageView } from './betBuilderResultsUtils'

type Props = {
  view: BetBuilderPageView
  onChange: (view: BetBuilderPageView) => void
}

export function BetBuilderViewSwitch({ view, onChange }: Props) {
  return (
    <div
      className="inline-flex overflow-hidden rounded-xl border border-slate-200 bg-slate-100/80 p-1 shadow-sm"
      role="tablist"
      aria-label="Modalità Bet Builder"
      data-testid="bet-builder-view-switch"
    >
      <button
        type="button"
        role="tab"
        aria-selected={view === 'pre-match'}
        data-testid="bet-builder-view-prematch"
        className={`min-h-10 rounded-lg px-3.5 text-sm font-semibold transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400 ${
          view === 'pre-match'
            ? 'bg-white text-slate-900 shadow-sm'
            : 'text-slate-600 hover:text-slate-900'
        }`}
        onClick={() => onChange('pre-match')}
      >
        Pre-match
      </button>
      <button
        type="button"
        role="tab"
        aria-selected={view === 'results'}
        data-testid="bet-builder-view-results"
        className={`min-h-10 rounded-lg px-3.5 text-sm font-semibold transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400 ${
          view === 'results'
            ? 'bg-white text-slate-900 shadow-sm'
            : 'text-slate-600 hover:text-slate-900'
        }`}
        onClick={() => onChange('results')}
      >
        Risultati
      </button>
    </div>
  )
}
