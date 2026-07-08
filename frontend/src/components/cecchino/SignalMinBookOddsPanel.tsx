import {
  SIGNAL_MIN_BOOK_ODDS_DISPLAY,
  SIGNAL_VALUE_FILTER_NOTE,
} from './signalMinBookOdds'

type SignalMinBookOddsPanelProps = {
  variant?: 'monitoring' | 'lab'
}

export function SignalMinBookOddsPanel({ variant = 'monitoring' }: SignalMinBookOddsPanelProps) {
  const isLab = variant === 'lab'
  return (
    <section
      className={
        isLab
          ? 'rounded-2xl border border-indigo-100 bg-gradient-to-br from-indigo-50/40 via-white to-slate-50/60 p-5 shadow-sm'
          : 'rounded-lg border border-slate-200 bg-white p-4'
      }
    >
      <h2 className="text-sm font-semibold text-slate-800">Soglie minime quota book</h2>
      <p className="mt-2 text-sm leading-relaxed text-slate-600">{SIGNAL_VALUE_FILTER_NOTE}</p>
      <div className="mt-3 flex flex-wrap gap-2">
        {SIGNAL_MIN_BOOK_ODDS_DISPLAY.map((item) => (
          <span
            key={item.label}
            className="inline-flex items-center rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs font-medium text-slate-700"
          >
            {item.label} ≥ {item.minOdd}
          </span>
        ))}
      </div>
      <p className="mt-3 text-xs text-slate-500">Soglie operative read-only — configurazione in step successivo.</p>
    </section>
  )
}
