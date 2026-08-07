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
  compact = false,
}: Props) {
  const source = payload.source ?? ''
  const isOfficial = payload.official === true || source === 'v5_official'
  const isFallback =
    source.includes('fallback') ||
    source === 'v4_fallback' ||
    payload.presentation === 'v4_fallback'

  const dq =
    payload.data_quality && typeof payload.data_quality === 'object'
      ? String(
          (payload.data_quality as { label?: string; status?: string }).label ??
            (payload.data_quality as { status?: string }).status ??
            '',
        )
      : ''

  return (
    <section aria-label="Intensità Goal v5" className={compact ? 'space-y-1.5' : 'space-y-3'}>
      <div className="flex flex-wrap items-center gap-2">
        <h3
          className={
            compact
              ? 'text-[10px] font-semibold uppercase tracking-wide text-slate-500'
              : 'text-xs font-semibold uppercase tracking-wide text-slate-500'
          }
        >
          Intensità Goal v5
        </h3>
        {isOfficial ? (
          <span className={`${bbBadge} border-sky-200 bg-sky-50 text-sky-900`}>V5 ufficiale</span>
        ) : isFallback ? (
          <span className={`${bbBadge} border-amber-200 bg-amber-50 text-amber-900`}>
            Fallback V4
          </span>
        ) : null}
      </div>

      <div className={`grid grid-cols-3 gap-1.5 ${compact ? '' : 'sm:gap-2'}`}>
        <div
          className={
            compact
              ? 'rounded-md border border-slate-100 bg-slate-50/60 px-2 py-1.5'
              : 'rounded-lg border border-slate-100 bg-slate-50/60 px-3 py-2'
          }
        >
          <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-400">
            Goal stimati
          </p>
          <p
            className={
              compact
                ? 'mt-0.5 text-sm font-semibold tabular-nums text-slate-900'
                : 'mt-0.5 text-lg font-semibold tabular-nums text-slate-900'
            }
          >
            {fmtGoals(payload.expected_total_goals)}
          </p>
        </div>
        <div
          className={
            compact
              ? 'rounded-md border border-slate-100 bg-slate-50/60 px-2 py-1.5'
              : 'rounded-lg border border-slate-100 bg-slate-50/60 px-3 py-2'
          }
        >
          <p className="truncate text-[10px] font-semibold uppercase tracking-wide text-slate-400">
            {marketLabel}
          </p>
          <p
            className={
              compact
                ? 'mt-0.5 text-sm font-semibold tabular-nums text-slate-900'
                : 'mt-0.5 text-lg font-semibold tabular-nums text-slate-900'
            }
          >
            {fmtPct(payload.probability_selection)}
          </p>
        </div>
        <div
          className={
            compact
              ? 'rounded-md border border-slate-100 bg-slate-50/60 px-2 py-1.5'
              : 'rounded-lg border border-slate-100 bg-slate-50/60 px-3 py-2'
          }
        >
          <p className="truncate text-[10px] font-semibold uppercase tracking-wide text-slate-400">
            {oppositeLabel(marketLabel)}
          </p>
          <p
            className={
              compact
                ? 'mt-0.5 text-sm font-semibold tabular-nums text-slate-900'
                : 'mt-0.5 text-lg font-semibold tabular-nums text-slate-900'
            }
          >
            {fmtPct(payload.probability_opposite)}
          </p>
        </div>
      </div>

      {!compact && dq ? <p className="text-xs text-slate-500">Data quality: {dq}</p> : null}
    </section>
  )
}
