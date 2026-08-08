import type { BetBuilderPriceValue } from '../../lib/cecchinoBetBuilderApi'
import { bbBadge, bbMetricCell } from './betBuilderStyles'

function fmtQuota(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return '—'
  return n.toFixed(2)
}

function fmtEdge(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return '—'
  const sign = n > 0 ? '+' : ''
  return `${sign}${n.toFixed(2)}%`
}

type Props = {
  price: BetBuilderPriceValue
  compact?: boolean
}

export function BetBuilderPriceBlock({ price, compact = false }: Props) {
  return (
    <section
      aria-label="Valore quota"
      className="space-y-2"
      data-testid={compact ? 'price-compact' : 'price-block'}
    >
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-[10px] font-semibold uppercase tracking-wide text-slate-400">
          Quota
        </h3>
        {price.present ? (
          <span className={`${bbBadge} border-emerald-200 bg-emerald-50 text-emerald-800`}>
            Valore quota
          </span>
        ) : (
          <span className="text-xs text-slate-500">Nessun valore quota rilevato</span>
        )}
      </div>

      <div className={`grid grid-cols-2 gap-2 ${compact ? '' : 'sm:grid-cols-4'}`}>
        <div className={bbMetricCell}>
          <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-400">Book</p>
          <p className="mt-0.5 text-lg font-semibold tabular-nums text-slate-900">
            {fmtQuota(price.quota_book)}
          </p>
          {price.quota_book != null ? (
            <p className="mt-0.5 text-[10px] text-slate-500" data-testid="book-provenance">
              {price.book_fallback_used
                ? `${price.bookmaker_name ?? 'Bet365'} · fallback`
                : price.bookmaker_name ?? 'Betfair'}
            </p>
          ) : (
            <p className="mt-0.5 text-[10px] text-slate-400" data-testid="book-provenance">
              N/D
            </p>
          )}
        </div>
        <div className={bbMetricCell}>
          <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-400">
            Cecchino
          </p>
          <p className="mt-0.5 text-lg font-semibold tabular-nums text-slate-900">
            {fmtQuota(price.quota_cecchino)}
          </p>
        </div>
        <div className={bbMetricCell}>
          <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-400">Edge</p>
          <p className="mt-0.5 text-base font-semibold tabular-nums text-slate-900">
            {fmtEdge(price.edge_pct)}
          </p>
        </div>
        <div className={bbMetricCell}>
          <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-400">Rating</p>
          <p className="mt-0.5 text-base font-semibold tabular-nums text-slate-900">
            {price.rating != null ? `${price.rating}` : '—'}
            {price.rating_label ? (
              <span className="ml-1 text-xs font-medium text-slate-600">
                · {price.rating_label}
              </span>
            ) : null}
          </p>
        </div>
      </div>
    </section>
  )
}
