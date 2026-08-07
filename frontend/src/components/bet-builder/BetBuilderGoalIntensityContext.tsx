import type { BetBuilderGoalIntensityContextPayload } from '../../lib/cecchinoBetBuilderApi'
import { bbBadge } from './betBuilderStyles'

type Props = {
  payload: BetBuilderGoalIntensityContextPayload
  marketLabel: string
  compact?: boolean
}

function fmtGoals(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return '—'
  return n.toFixed(2)
}

function fmtPct(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return '—'
  const pct = n <= 1 ? n * 100 : n
  return `${pct.toFixed(1)}%`
}

function oppositeLabel(marketLabel: string): string {
  if (marketLabel.startsWith('Over')) return marketLabel.replace('Over', 'Under')
  if (marketLabel.startsWith('Under')) return marketLabel.replace('Under', 'Over')
  return 'Opposite'
}

export function BetBuilderGoalIntensityContext({
  payload,
  marketLabel,
}: Props) {
  const source = payload.source ?? ''
  const isOfficial = payload.official === true || source === 'v5_official'
  const isFallback =
    source.includes('fallback') ||
    source === 'v4_fallback' ||
    payload.presentation === 'v4_fallback'

  return (
    <section aria-label="Intensità Goal v5" className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
          Goal Intensity V5
        </h3>
        {isOfficial ? (
          <span className={`${bbBadge} border-sky-200 bg-sky-50 text-sky-900`}>V5 ufficiale</span>
        ) : isFallback ? (
          <span className={`${bbBadge} border-amber-200 bg-amber-50 text-amber-900`}>
            Fallback V4
          </span>
        ) : null}
      </div>

      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
        <div className="rounded-lg border border-slate-100 bg-slate-50/70 px-2.5 py-2">
          <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-400">
            Expected
          </p>
          <p className="mt-1 text-lg font-semibold tabular-nums text-slate-900">
            {fmtGoals(payload.expected_total_goals)}
          </p>
        </div>
        <div className="rounded-lg border border-slate-100 bg-slate-50/70 px-2.5 py-2">
          <p className="truncate text-[10px] font-semibold uppercase tracking-wide text-slate-400">
            Selected · {marketLabel}
          </p>
          <p className="mt-1 text-lg font-semibold tabular-nums text-slate-900">
            {fmtPct(payload.probability_selection)}
          </p>
        </div>
        <div className="col-span-2 rounded-lg border border-slate-100 bg-slate-50/70 px-2.5 py-2 sm:col-span-1">
          <p className="truncate text-[10px] font-semibold uppercase tracking-wide text-slate-400">
            Opposite · {oppositeLabel(marketLabel)}
          </p>
          <p className="mt-1 text-lg font-semibold tabular-nums text-slate-900">
            {fmtPct(payload.probability_opposite)}
          </p>
        </div>
      </div>
    </section>
  )
}
