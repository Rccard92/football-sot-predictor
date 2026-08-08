import type { BetBuilderResultsSummary } from '../../lib/cecchinoBetBuilderApi'
import { bbCard, bbCardPadding } from './betBuilderStyles'
import { formatWinRate } from './betBuilderResultsUtils'

type Props = {
  summary: BetBuilderResultsSummary
  onFilterLost: () => void
}

function Kpi({
  label,
  value,
  testId,
  onClick,
  emphasize,
}: {
  label: string
  value: string | number
  testId: string
  onClick?: () => void
  emphasize?: 'lost' | 'won' | null
}) {
  const base =
    'min-w-0 rounded-xl border border-slate-100 bg-slate-50/80 px-3 py-2.5 text-left'
  const clickable = onClick
    ? 'cursor-pointer transition hover:border-rose-200 hover:bg-rose-50/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-rose-300'
    : ''
  const accent =
    emphasize === 'lost'
      ? 'border-rose-100'
      : emphasize === 'won'
        ? 'border-emerald-100'
        : ''

  const content = (
    <>
      <p className="text-[11px] font-medium uppercase tracking-wide text-slate-500">{label}</p>
      <p className="mt-0.5 text-lg font-semibold tabular-nums text-slate-900 sm:text-xl" data-testid={testId}>
        {value}
      </p>
    </>
  )

  if (onClick) {
    return (
      <button type="button" className={`${base} ${clickable} ${accent}`} onClick={onClick} data-testid={`${testId}-btn`}>
        {content}
      </button>
    )
  }
  return <div className={`${base} ${accent}`}>{content}</div>
}

export function BetBuilderResultsSummary({ summary, onFilterLost }: Props) {
  const livePending = summary.live_or_pending ?? summary.pending
  return (
    <section
      className={`${bbCard} ${bbCardPadding}`}
      data-testid="bet-builder-results-summary"
      aria-label="KPI monitoraggio risultati"
    >
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
        <Kpi label="Prediction" value={summary.primary_predictions} testId="results-kpi-predictions" />
        <Kpi label="Concluse" value={summary.settled} testId="results-kpi-settled" />
        <Kpi label="Vinte" value={summary.won} testId="results-kpi-won" emphasize="won" />
        <Kpi
          label="Perse"
          value={summary.lost}
          testId="results-kpi-lost"
          emphasize="lost"
          onClick={onFilterLost}
        />
        <Kpi label="Win Rate" value={formatWinRate(summary.win_rate)} testId="results-kpi-winrate" />
        <Kpi label="Live / In attesa" value={livePending} testId="results-kpi-pending" />
      </div>
      <p className="mt-2 text-xs text-slate-500" data-testid="results-kpi-primary-note">
        KPI sulla predizione madre (Evidence Sort V2). Le opportunity secondarie sono solo diagnostiche.
      </p>
    </section>
  )
}
