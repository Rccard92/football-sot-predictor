import type { BetBuilderResultsSummary } from '../../lib/cecchinoBetBuilderApi'
import { bbCard, bbCardPadding } from './betBuilderStyles'
import {
  formatProfitUnits,
  formatRoiPct,
  formatWinRate,
  signedMetricTone,
} from './betBuilderResultsUtils'

type Props = {
  summary: BetBuilderResultsSummary
  onFilterLost: () => void
}

function valueToneClass(tone: 'positive' | 'negative' | 'neutral' | undefined): string {
  if (tone === 'positive') return 'text-emerald-700'
  if (tone === 'negative') return 'text-rose-700'
  return 'text-slate-900'
}

function Kpi({
  label,
  value,
  testId,
  onClick,
  emphasize,
  tone,
}: {
  label: string
  value: string | number
  testId: string
  onClick?: () => void
  emphasize?: 'lost' | 'won' | null
  tone?: 'positive' | 'negative' | 'neutral'
}) {
  const base =
    'min-w-0 rounded-xl border border-slate-100 bg-slate-50/80 px-2.5 py-2.5 text-left'
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
      <p className="text-[10px] font-medium uppercase tracking-wide text-slate-500 lg:text-[11px]">
        {label}
      </p>
      <p
        className={`mt-0.5 text-lg font-semibold tabular-nums lg:text-xl ${valueToneClass(tone)}`}
        data-testid={testId}
      >
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
  const profitTone = signedMetricTone(summary.profit_units)
  const roiTone = signedMetricTone(summary.roi_pct)

  return (
    <section
      className={`${bbCard} ${bbCardPadding}`}
      data-testid="bet-builder-results-summary"
      aria-label="KPI monitoraggio risultati"
    >
      <div className="grid grid-cols-2 gap-2 lg:grid-cols-8">
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
        <Kpi
          label="Profitto"
          value={formatProfitUnits(summary.profit_units)}
          testId="results-kpi-profit"
          tone={profitTone}
        />
        <Kpi
          label="ROI"
          value={formatRoiPct(summary.roi_pct)}
          testId="results-kpi-roi"
          tone={roiTone}
        />
        <Kpi label="Live / In attesa" value={livePending} testId="results-kpi-pending" />
      </div>
      <p className="mt-2 text-xs text-slate-500" data-testid="results-kpi-primary-note">
        KPI sulla predizione madre (Evidence Sort V2). Le opportunity secondarie sono solo diagnostiche.
      </p>
      <p className="mt-0.5 text-xs text-slate-500" data-testid="results-kpi-flat-stake-note">
        ROI e Profitto: flat stake teorico 1u sulle primary concluse con quota Book. Quote N/D escluse.
      </p>
    </section>
  )
}
