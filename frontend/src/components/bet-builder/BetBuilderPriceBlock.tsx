import type { BetBuilderPriceValue } from '../../lib/cecchinoBetBuilderApi'
import { bbBadge } from './betBuilderStyles'

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
}

export function BetBuilderPriceBlock({ price }: Props) {
  return (
    <section aria-label="Valore quota" className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">Quota</h3>
        {price.present ? (
          <span className={`${bbBadge} border-emerald-200 bg-emerald-50 text-emerald-800`}>
            Valore quota
          </span>
        ) : (
          <span className="text-xs text-slate-500">Nessun valore quota rilevato</span>
        )}
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">Book</p>
          <p className="mt-0.5 text-xl font-semibold tabular-nums text-slate-900">
            {fmtQuota(price.quota_book)}
          </p>
        </div>
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">Cecchino</p>
          <p className="mt-0.5 text-xl font-semibold tabular-nums text-slate-900">
            {fmtQuota(price.quota_cecchino)}
          </p>
        </div>
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">Edge</p>
          <p className="mt-0.5 text-lg font-semibold tabular-nums text-slate-900">
            {fmtEdge(price.edge_pct)}
          </p>
        </div>
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">Rating</p>
          <p className="mt-0.5 text-lg font-semibold tabular-nums text-slate-900">
            {price.rating != null ? `${price.rating}` : '—'}
            {price.rating_label ? (
              <span className="ml-1 text-sm font-medium text-slate-600">· {price.rating_label}</span>
            ) : null}
          </p>
        </div>
      </div>
    </section>
  )
}
