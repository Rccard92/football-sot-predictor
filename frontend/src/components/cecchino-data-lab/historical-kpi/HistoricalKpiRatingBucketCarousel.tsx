import type {
  HistoricalKpiRatingBucket,
  HistoricalKpiSignalsFilters,
} from '../../../lib/cecchinoLabApi'
import {
  formatOdds,
  formatProfit,
  formatRoi,
  formatWinRate,
  quoteTypeMatchesFilter,
  roiColorClass,
} from './historicalKpiUtils'

type Props = {
  buckets: HistoricalKpiRatingBucket[]
  activeRatingBucket?: string
  quoteType: HistoricalKpiSignalsFilters['quote_type']
  onSelect: (ratingBucket: string) => void
}

export function HistoricalKpiRatingBucketCarousel({
  buckets,
  activeRatingBucket,
  quoteType,
  onSelect,
}: Props) {
  const filtered = buckets.filter((b) => quoteTypeMatchesFilter(b.quote_type, quoteType))

  if (filtered.length === 0) {
    return (
      <p className="text-sm text-[var(--lab-muted)]">Nessuna fascia rating con dati per i filtri attivi.</p>
    )
  }

  return (
    <section>
      <h3 className="mb-3 text-lg font-semibold">Fasce rating</h3>
      <div className="flex gap-3 overflow-x-auto pb-2">
        {filtered.map((b) => {
          const active = activeRatingBucket === b.rating_bucket
          const avgOdds = b.average_odds_played ?? b.average_odds_won
          return (
            <button
              key={`${b.rating_bucket}-${b.quote_type}`}
              type="button"
              onClick={() => onSelect(b.rating_bucket)}
              className="min-w-[148px] shrink-0 rounded-xl border p-3 text-left transition"
              style={{
                borderColor: active ? 'var(--lab-cyan)' : 'var(--lab-border)',
                background: active ? 'rgba(46,230,255,0.1)' : 'var(--lab-surface)',
                boxShadow: active ? '0 0 0 1px rgba(46,230,255,0.35)' : undefined,
              }}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="text-sm font-semibold text-[var(--lab-cyan)]">{b.rating_bucket}</span>
                {quoteType === 'all' ? (
                  <span
                    className={`rounded px-1.5 py-0.5 text-[10px] ${
                      b.quote_type === 'real' ? 'lab-quote-real' : 'lab-quote-derived'
                    }`}
                  >
                    {b.quote_type === 'real' ? 'Reale' : 'Derivata'}
                  </span>
                ) : null}
              </div>
              <dl className="mt-2 space-y-1 text-xs text-[var(--lab-muted)]">
                <div className="flex justify-between gap-2">
                  <dt>Profitto</dt>
                  <dd className={roiColorClass(b.roi_pct)}>{formatProfit(b.profit_units)}</dd>
                </div>
                <div className="flex justify-between gap-2">
                  <dt>ROI</dt>
                  <dd className={roiColorClass(b.roi_pct)}>{formatRoi(b.roi_pct)}</dd>
                </div>
                <div className="flex justify-between gap-2">
                  <dt>Win rate</dt>
                  <dd>{formatWinRate(b.win_rate_pct)}</dd>
                </div>
                <div className="flex justify-between gap-2">
                  <dt>Valutati</dt>
                  <dd>{b.evaluated_count}</dd>
                </div>
                <div className="flex justify-between gap-2">
                  <dt>Quota media</dt>
                  <dd>{formatOdds(avgOdds)}</dd>
                </div>
              </dl>
            </button>
          )
        })}
      </div>
    </section>
  )
}
