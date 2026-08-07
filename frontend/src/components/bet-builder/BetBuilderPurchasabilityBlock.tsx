import type { BetBuilderPurchasabilityV31 } from '../../lib/cecchinoBetBuilderApi'
import { bbBadge } from './betBuilderStyles'

type Props = {
  purchasability: BetBuilderPurchasabilityV31
  compact?: boolean
}

export function BetBuilderPurchasabilityBlock({ purchasability, compact = false }: Props) {
  const score = purchasability.score
  const hasScore = score != null && !Number.isNaN(score)
  const clamped = hasScore ? Math.max(0, Math.min(100, score)) : 0
  const quality = purchasability.calculation_quality

  if (compact) {
    return (
      <div
        className="flex flex-wrap items-center gap-2"
        aria-label="Acquistabilità V3.1"
        data-testid="purchasability-compact"
      >
        <p className="text-xl font-semibold tabular-nums tracking-tight text-slate-900">
          {hasScore ? Math.round(score) : 'N/D'}
          {hasScore ? <span className="text-sm font-medium text-slate-500"> / 100</span> : null}
        </p>
        {purchasability.class ? (
          <span className="text-sm font-semibold text-slate-700">{purchasability.class}</span>
        ) : null}
        {quality === 'provisional' ? (
          <span className={`${bbBadge} border-amber-200 bg-amber-50 text-amber-900`}>
            Provvisoria
          </span>
        ) : null}
      </div>
    )
  }

  return (
    <section aria-label="Acquistabilità V3.1" className="space-y-3 rounded-lg border border-slate-200 bg-slate-50/80 p-3 sm:p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
          Acquistabilità V3.1
        </h3>
        <div className="flex flex-wrap gap-1.5">
          {quality === 'provisional' ? (
            <span className={`${bbBadge} border-amber-200 bg-amber-50 text-amber-900`}>
              Provvisoria
            </span>
          ) : quality === 'full' ? (
            <span className={`${bbBadge} border-slate-200 bg-white text-slate-700`}>Completa</span>
          ) : null}
        </div>
      </div>

      <div className="flex items-end gap-3">
        <p className="text-3xl font-semibold tabular-nums tracking-tight text-slate-900">
          {hasScore ? Math.round(score) : 'N/D'}
          {hasScore ? <span className="text-lg font-medium text-slate-500"> / 100</span> : null}
        </p>
        {purchasability.class ? (
          <p className="mb-1 text-sm font-semibold text-slate-700">{purchasability.class}</p>
        ) : null}
      </div>

      <div
        className="h-2.5 overflow-hidden rounded-full bg-slate-200"
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={hasScore ? Math.round(clamped) : undefined}
        aria-valuetext={hasScore ? `${Math.round(clamped)} su 100` : 'Non disponibile'}
        aria-label="Score Acquistabilità V3.1"
      >
        <div
          className="h-full rounded-full bg-slate-800 transition-[width]"
          style={{ width: hasScore ? `${clamped}%` : '0%' }}
        />
      </div>

      {purchasability.reading_short ? (
        <p className="text-xs leading-relaxed text-slate-600">{purchasability.reading_short}</p>
      ) : null}
    </section>
  )
}
